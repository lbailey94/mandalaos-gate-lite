#!/usr/bin/env python3
"""Minimal MCP server for the gate-lite control surface (v0).

JSON-RPC 2.0 over newline-delimited stdio, or loopback HTTP (Streamable HTTP
subset: POST /mcp with JSON or SSE response, GET -> 405). No third-party MCP
SDK dependency; the protocol subset used here is the tools surface every
client exercises.

Run (stdio): python3 -m gate_lite.mcp_server --state ./state --tenant dogfood
Run (http):  python3 -m gate_lite.mcp_server --state ./state --tenant dogfood \
                 --transport http --host 127.0.0.1 --port 8765
"""
import argparse
import json
import os
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from continuity_receipt import verify_bundle  # noqa: E402
from gate_lite.models import SLOT_CLASSES  # noqa: E402
from gate_lite.orchestrator import EmitterError, Orchestrator, build_runner  # noqa: E402
from gate_lite.tokens import verify_pass  # noqa: E402

PROTOCOL_VERSION = "2025-06-18"
SERVER_NAME = "gate-lite-mcp"
SERVER_VERSION = "0.1.0"

TOOLS = [
    {
        "name": "mandala.pass",
        "description": (
            "Buy a time-boxed governed pass on this gate. Returns a pass token, "
            "slot id, quotas, expiry, and the continuity receipt id."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent": {"type": "string", "description": "agent did:key"},
                "principal": {"type": "string"},
                "minutes": {"type": "integer", "default": 90},
                "class": {"type": "string", "enum": sorted(SLOT_CLASSES)},
                "spend_minor": {"type": "integer"},
                "idempotency_key": {"type": "string"},
            },
            "required": ["agent"],
        },
    },
    {
        "name": "mandala.exec",
        "description": (
            "Execute a payload inside a pass slot. Emits decision + execution "
            "receipts; returns exit code, stdout hash, and receipt ids. Payload "
            "is a command or a declared-execution envelope with default-deny egress."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent": {"type": "string"},
                "slot": {"type": "string"},
                "payload_ref": {"type": "string"},
                "token": {"type": "string", "description": "pass token (optional in v0 dogfood)"},
                "idempotency_key": {"type": "string"},
            },
            "required": ["agent", "slot", "payload_ref"],
        },
    },
    {
        "name": "mandala.settle",
        "description": (
            "Record settlement for a slot (invoice or x402 lane). Enforces the "
            "pass spend cap and emits delivery + settlement receipts."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "slot": {"type": "string"},
                "rail": {"type": "string", "enum": ["invoice", "x402", "stripe", "offchain", "none"]},
                "rail_ref": {"type": "string"},
                "minor": {"type": "integer"},
                "currency": {"type": "string", "default": "USD"},
            },
            "required": ["slot", "rail_ref", "minor"],
        },
    },
    {
        "name": "mandala.terminate",
        "description": "Terminate a slot and seal its continuity receipt chain.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "slot": {"type": "string"},
                "reason": {"type": "string", "enum": ["completed", "budget_exhausted", "time_expired", "killed", "error"]},
            },
            "required": ["slot"],
        },
    },
    {
        "name": "mandala.kill",
        "description": (
            "Operator kill switch: stops a live run within wait_s seconds "
            "(SIGTERM, escalate SIGKILL) and records task.termination "
            "kill_signal=operator."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "slot": {"type": "string"},
                "signal": {"type": "string", "default": "SIGTERM"},
                "wait_s": {"type": "number", "default": 5.0},
            },
            "required": ["slot"],
        },
    },
    {
        "name": "mandala.destroy",
        "description": "Destroy a slot (terminate with reason destroyed; key erasure semantics documented).",
        "inputSchema": {"type": "object", "properties": {"slot": {"type": "string"}}, "required": ["slot"]},
    },
    {
        "name": "mandala.status",
        "description": "Read a slot's state, quotas, and task id.",
        "inputSchema": {"type": "object", "properties": {"slot": {"type": "string"}}, "required": ["slot"]},
    },
    {
        "name": "mandala.list",
        "description": "List this tenant's slots.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "mandala.receipt",
        "description": "Export a task's continuity receipt bundle; set verify=true for the verdict.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string"},
                "verify": {"type": "boolean", "default": False},
            },
            "required": ["task_id"],
        },
    },
    {
        "name": "mandala.templates",
        "description": "List available slot templates (v0: slot classes).",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "mandala.snapshot",
        "description": (
            "Freeze a slot with a filesystem snapshot of its workspace "
            "(delivery.attestation receipt; store image is gate-hard scope)."
        ),
        "inputSchema": {"type": "object", "properties": {"slot": {"type": "string"}}, "required": ["slot"]},
    },
    {
        "name": "mandala.restore",
        "description": (
            "Materialize a snapshot into a placed slot before exec "
            "(filesystem restore; emits a delivery.attestation)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"slot": {"type": "string"}, "snapshot_id": {"type": "string"}},
            "required": ["slot", "snapshot_id"],
        },
    },
    {
        "name": "mandala.sweep",
        "description": "Seal this tenant's past-expiry slots with time_expired termination receipts.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def _result(payload: dict) -> dict:
    return {"content": [{"type": "text", "text": json.dumps(payload, default=str)}]}


def _tool_error(code: str, detail: str) -> dict:
    return {
        "content": [{"type": "text", "text": json.dumps({"error": code, "detail": detail})}],
        "isError": True,
    }


class McpServer:
    def __init__(self, orchestrator: Orchestrator, tenant_id: str):
        self.orch = orchestrator
        self.tenant_id = tenant_id

    def handle(self, message: dict) -> dict | None:
        method = message.get("method")
        request_id = message.get("id")

        if method == "initialize":
            params = message.get("params") or {}
            requested = params.get("protocolVersion") or PROTOCOL_VERSION
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "protocolVersion": requested,
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                },
            }
        if method in ("notifications/initialized", "notifications/cancelled"):
            return None
        if method == "ping":
            return {"jsonrpc": "2.0", "id": request_id, "result": {}}
        if method == "tools/list":
            return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": TOOLS}}
        if method == "tools/call":
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": self._call(message.get("params") or {}),
            }
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32601, "message": f"method not found: {method}"},
        }

    def _call(self, params: dict) -> dict:
        name = params.get("name")
        args = params.get("arguments") or {}
        try:
            if name == "mandala.pass":
                spend_cap = None
                if args.get("spend_minor"):
                    spend_cap = {"minor": int(args["spend_minor"]), "currency": "USD"}
                return _result(
                    self.orch.pass_(
                        self.tenant_id,
                        args["agent"],
                        minutes=int(args.get("minutes", 90)),
                        slot_class=args.get("class", "small"),
                        spend_cap=spend_cap,
                        principal_id=args.get("principal"),
                        idempotency_key=args.get("idempotency_key"),
                    )
                )
            if name == "mandala.exec":
                token = args.get("token")
                if token:
                    claims = verify_pass(token, self.orch.gate_did)
                    if claims.get("sub") != args.get("agent"):
                        return _tool_error("token_subject_mismatch", "token is bound to another agent")
                    if int(claims.get("exp", 0)) < time.time():
                        return _tool_error("pass_expired", "pass token expired")
                return _result(
                    self.orch.exec_(
                        self.tenant_id,
                        args["slot"],
                        args["payload_ref"],
                        idempotency_key=args.get("idempotency_key"),
                    )
                )
            if name == "mandala.settle":
                return _result(
                    self.orch.settle(
                        self.tenant_id,
                        args["slot"],
                        args.get("rail", "invoice"),
                        args["rail_ref"],
                        int(args["minor"]),
                        currency=args.get("currency", "USD"),
                    )
                )
            if name in ("mandala.terminate", "mandala.destroy"):
                reason = args.get("reason") or ("destroyed" if name == "mandala.destroy" else "completed")
                return _result(self.orch.terminate(self.tenant_id, args["slot"], reason=reason))
            if name == "mandala.kill":
                return _result(
                    self.orch.kill(
                        self.tenant_id,
                        args["slot"],
                        signal_name=args.get("signal", "SIGTERM"),
                        wait_s=float(args.get("wait_s", 5.0)),
                    )
                )
            if name == "mandala.status":
                return _result(self.orch.status(self.tenant_id, args["slot"]))
            if name == "mandala.list":
                return _result({"slots": self.orch.list_(self.tenant_id)})
            if name == "mandala.receipt":
                bundle = self.orch.receipt(args["task_id"])
                if args.get("verify"):
                    return _result({"verdict": verify_bundle(bundle).as_dict(), "bundle": bundle})
                return _result({"bundle": bundle})
            if name == "mandala.templates":
                return _result(
                    {"templates": [{"name": key, "quotas": value} for key, value in SLOT_CLASSES.items()]}
                )
            if name == "mandala.snapshot":
                return _result(self.orch.snapshot(self.tenant_id, args["slot"]))
            if name == "mandala.restore":
                return _result(self.orch.restore(self.tenant_id, args["slot"], args["snapshot_id"]))
            if name == "mandala.sweep":
                return _result(self.orch.sweep_expired(self.tenant_id))
            return _tool_error("unknown_tool", f"no such tool: {name}")
        except EmitterError as exc:
            return _tool_error("emitter_unavailable", str(exc))
        except KeyError as exc:
            return _tool_error("not_found", str(exc))
        except PermissionError as exc:
            return _tool_error("permission_denied", str(exc))
        except ValueError as exc:
            return _tool_error("invalid", str(exc))


class McpHttpServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, mcp: McpServer, auth_token: str | None = None):
        super().__init__(address, McpHttpHandler)
        self.mcp = mcp
        self.auth_token = auth_token
        self.lock = threading.Lock()


class McpHttpHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = f"{SERVER_NAME}/{SERVER_VERSION}"
    disable_nagle_algorithm = True

    def log_message(self, fmt, *args):  # noqa: A003 - stdlib hook
        pass

    def _authorized(self) -> bool:
        token = self.server.auth_token
        if not token:
            return True
        return self.headers.get("Authorization") == f"Bearer {token}"

    def _send(self, code: int, body: bytes, content_type: str, extra: dict | None = None):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _send_json(self, code: int, payload: dict, extra: dict | None = None):
        self._send(code, json.dumps(payload).encode("utf-8"), "application/json", extra)

    def do_GET(self):  # noqa: N802 - stdlib hook
        if self.path != "/mcp":
            self._send_json(404, {"error": "not found"})
            return
        self._send_json(
            405,
            {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "GET SSE stream not offered; use POST"}},
            {"Allow": "POST"},
        )

    def do_POST(self):  # noqa: N802 - stdlib hook
        if self.path != "/mcp":
            self._send_json(404, {"error": "not found"})
            return
        if not self._authorized():
            self._send_json(401, {"error": "unauthorized"}, {"WWW-Authenticate": "Bearer"})
            return
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length)
        try:
            message = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._send_json(
                200, {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}
            )
            return
        if not isinstance(message, dict):
            self._send_json(
                200, {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "invalid request"}}
            )
            return

        is_notification = "id" not in message
        with self.server.lock:
            response = self.server.mcp.handle(message)

        headers = {}
        session_id = self.headers.get("Mcp-Session-Id")
        if message.get("method") == "initialize" and response is not None:
            session_id = session_id or str(uuid.uuid4())
        if session_id:
            headers["Mcp-Session-Id"] = session_id

        if response is None or is_notification:
            self._send(202, b"", "application/json", headers)
            return

        accept = self.headers.get("Accept", "")
        if "text/event-stream" in accept:
            body = f"event: message\ndata: {json.dumps(response)}\n\n".encode("utf-8")
            self._send(200, body, "text/event-stream", headers)
        else:
            self._send_json(200, response, headers)


def serve_http(mcp: McpServer, host: str, port: int, auth_token: str | None = None) -> int:
    server = McpHttpServer((host, port), mcp, auth_token)
    actual_port = server.server_address[1]
    banner = {
        "transport": "http",
        "host": host,
        "port": actual_port,
        "endpoint": f"http://{host}:{actual_port}/mcp",
        "auth": "bearer" if auth_token else "none",
    }
    print(json.dumps(banner), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def serve_stdio(mcp: McpServer) -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            print(
                json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}),
                flush=True,
            )
            continue
        response = mcp.handle(message)
        if response is not None:
            print(json.dumps(response), flush=True)
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="gate-lite-mcp")
    parser.add_argument("--state", default="./gate-state")
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--gate-id", default="gate-lite-1")
    parser.add_argument("--runner", default=None)
    parser.add_argument("--slice", action="store_true", help="systemd slice quotas (G2)")
    parser.add_argument("--transport", choices=("stdio", "http"), default="stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--token", default=None, help="optional bearer token for the HTTP transport")
    args = parser.parse_args(argv)

    runner_path = args.runner or os.environ.get("WM_GATELITE_RUNNER")
    slice_mode = args.slice or os.environ.get("WM_GATELITE_SLICE") == "1"
    runner = build_runner(runner_path, slice_mode)
    orchestrator = Orchestrator(args.state, gate_id=args.gate_id, runner=runner)
    server = McpServer(orchestrator, args.tenant)

    if args.transport == "http":
        return serve_http(server, args.host, args.port, args.token)
    return serve_stdio(server)


if __name__ == "__main__":
    sys.exit(main())
