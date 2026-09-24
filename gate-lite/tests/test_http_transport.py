"""MCP over loopback HTTP (Streamable HTTP subset) tests."""
import json
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from continuity_receipt import keys  # noqa: E402
from gate_lite.mcp_server import McpHttpServer, McpServer  # noqa: E402
from gate_lite.orchestrator import Orchestrator  # noqa: E402


def make_server(state_dir: Path) -> tuple[McpServer, str]:
    agent_did, _ = keys.generate(keys.deterministic_seed("http-agent"))
    gate_did, gate_key = keys.generate(keys.deterministic_seed("gate-http"))
    orch = Orchestrator(state_dir, gate_id="gate-http", gate_key=gate_key, gate_did=gate_did)
    orch.add_tenant("dogfood", [agent_did])
    return McpServer(orch, "dogfood"), agent_did


def payload(response: dict) -> dict:
    return json.loads(response["result"]["content"][0]["text"])


def rpc(port: int, message: dict | None = None, headers: dict | None = None,
        method: str = "POST", path: str = "/mcp", raw: bytes | None = None):
    data = raw if raw is not None else json.dumps(message).encode("utf-8")
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=data if method == "POST" else None,
        method=method,
        headers=headers or {},
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read()


def start_http(mcp: McpServer, token: str | None = None):
    server = McpHttpServer(("127.0.0.1", 0), mcp, token)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, port, thread


class TestHttpTransport(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.state = Path(self._tmp.name)
        self.mcp, self.agent_did = make_server(self.state)
        self.server, self.port, self.thread = start_http(self.mcp)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self._tmp.cleanup()

    def initialize(self, accept: str | None = None):
        headers = {"Content-Type": "application/json"}
        if accept:
            headers["Accept"] = accept
        return rpc(
            self.port,
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
            headers=headers,
        )

    def test_initialize_tools_list_and_session_header(self):
        status, headers, body = self.initialize()
        self.assertEqual(status, 200)
        self.assertEqual(headers.get("Content-Type"), "application/json")
        session = headers.get("Mcp-Session-Id")
        self.assertTrue(session, "initialize must issue a session id")
        initialized = json.loads(body)
        self.assertEqual(initialized["result"]["serverInfo"]["name"], "gate-lite-mcp")

        status, _, body = rpc(
            self.port,
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            headers={"Content-Type": "application/json", "Mcp-Session-Id": session},
        )
        self.assertEqual(status, 200)
        tools = json.loads(body)["result"]["tools"]
        # Surface count follows TOOLS; mandala.pass.verify joined in S2b.
        self.assertEqual(len(tools), 14)
        names = {tool["name"] for tool in tools}
        self.assertIn("mandala.kill", names)
        self.assertIn("mandala.restore", names)
        self.assertIn("mandala.pass.verify", names)

    def test_sse_response_mode(self):
        status, headers, body = self.initialize(accept="text/event-stream")
        self.assertEqual(status, 200)
        self.assertEqual(headers.get("Content-Type"), "text/event-stream")
        text = body.decode("utf-8")
        self.assertTrue(text.startswith("event: message\ndata: "))
        first = json.loads(text.split("data: ", 1)[1].split("\n", 1)[0])
        self.assertIn("serverInfo", first["result"])

    def test_notification_returns_202(self):
        status, _, body = rpc(
            self.port, {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}
        )
        self.assertEqual(status, 202)
        self.assertEqual(body, b"")

    def test_full_flow_over_http_verifies_trusted(self):
        _, headers, _ = self.initialize()
        session = headers["Mcp-Session-Id"]
        auth = {"Content-Type": "application/json", "Mcp-Session-Id": session}

        def call(call_id: int, name: str, arguments: dict) -> dict:
            status, _, body = rpc(
                self.port,
                {"jsonrpc": "2.0", "id": call_id, "method": "tools/call", "params": {"name": name, "arguments": arguments}},
                headers=auth,
            )
            self.assertEqual(status, 200)
            return payload(json.loads(body))

        passed = call(2, "mandala.pass", {"agent": self.agent_did, "minutes": 30, "spend_minor": 1000})
        executed = call(3, "mandala.exec", {"agent": self.agent_did, "slot": passed["slot_id"], "payload_ref": "echo http", "token": passed["token"]})
        self.assertEqual(executed["exit"], 0)
        call(4, "mandala.settle", {"slot": passed["slot_id"], "rail_ref": "inv-http", "minor": 200})
        terminated = call(5, "mandala.terminate", {"slot": passed["slot_id"]})
        receipt = call(6, "mandala.receipt", {"task_id": terminated["task_id"], "verify": True})
        self.assertEqual(receipt["verdict"]["verdict"], "TRUSTED", receipt["verdict"]["errors"])
        self.assertEqual(receipt["verdict"]["summary"]["receipts"], 6)

    def test_get_and_unknown_paths(self):
        status, headers, _ = rpc(self.port, method="GET")
        self.assertEqual(status, 405)
        self.assertEqual(headers.get("Allow"), "POST")
        status, _, _ = rpc(self.port, {"jsonrpc": "2.0", "id": 1, "method": "ping"}, path="/nope")
        self.assertEqual(status, 404)

    def test_parse_error_and_invalid_request(self):
        status, _, body = rpc(self.port, raw=b"{not json")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["error"]["code"], -32700)
        status, _, body = rpc(self.port, raw=json.dumps([1, 2, 3]).encode())
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["error"]["code"], -32600)

    def test_auth_token_enforced(self):
        server, port, _ = start_http(McpServer(self.mcp.orch, "dogfood"), token="s3cret")
        try:
            status, _, _ = rpc(port, {"jsonrpc": "2.0", "id": 1, "method": "ping"})
            self.assertEqual(status, 401)
            status, _, _ = rpc(
                port,
                {"jsonrpc": "2.0", "id": 1, "method": "ping"},
                headers={"Authorization": "Bearer wrong"},
            )
            self.assertEqual(status, 401)
            status, _, body = rpc(
                port,
                {"jsonrpc": "2.0", "id": 1, "method": "ping"},
                headers={"Authorization": "Bearer s3cret"},
            )
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body)["result"], {})
        finally:
            server.shutdown()
            server.server_close()


class TestHttpSubprocess(unittest.TestCase):
    def test_subprocess_http_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            _server, agent_did = make_server(state)
            proc = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "gate_lite.mcp_server",
                    "--state",
                    str(state),
                    "--tenant",
                    "dogfood",
                    "--demo",
                    "--transport",
                    "http",
                    "--port",
                    "0",
                ],
                cwd=str(ROOT),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            try:
                banner = json.loads(proc.stdout.readline())
                port = banner["port"]
                self.assertEqual(banner["transport"], "http")

                status, headers, body = rpc(
                    port,
                    {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                    headers={"Content-Type": "application/json"},
                )
                self.assertEqual(status, 200)
                session = headers["Mcp-Session-Id"]
                auth = {"Content-Type": "application/json", "Mcp-Session-Id": session}

                status, _, body = rpc(
                    port,
                    {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                     "params": {"name": "mandala.pass", "arguments": {"agent": agent_did}}},
                    headers=auth,
                )
                passed = payload(json.loads(body))
                status, _, body = rpc(
                    port,
                    {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                     "params": {"name": "mandala.terminate", "arguments": {"slot": passed["slot_id"]}}},
                    headers=auth,
                )
                terminated = payload(json.loads(body))
                status, _, body = rpc(
                    port,
                    {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                     "params": {"name": "mandala.receipt",
                                "arguments": {"task_id": terminated["task_id"], "verify": True}}},
                    headers=auth,
                )
                receipt = payload(json.loads(body))
                self.assertEqual(receipt["verdict"]["verdict"], "TRUSTED", receipt["verdict"]["errors"])
            finally:
                proc.terminate()
                proc.wait(timeout=10)


if __name__ == "__main__":
    unittest.main(verbosity=2)
