"""MCP control-surface tests: in-process protocol + subprocess stdio e2e."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from continuity_receipt import keys  # noqa: E402
from gate_lite.mcp_server import TOOLS, McpServer  # noqa: E402
from gate_lite.orchestrator import Orchestrator  # noqa: E402

EXPECTED_TOOLS = {
    "mandala.pass",
    "mandala.exec",
    "mandala.settle",
    "mandala.terminate",
    "mandala.kill",
    "mandala.destroy",
    "mandala.status",
    "mandala.list",
    "mandala.receipt",
    "mandala.templates",
    "mandala.snapshot",
    "mandala.restore",
    "mandala.sweep",
}


def make_server(state_dir: Path) -> tuple[McpServer, str]:
    agent_did, _ = keys.generate(keys.deterministic_seed("mcp-agent"))
    gate_did, gate_key = keys.generate(keys.deterministic_seed("gate-mcp"))
    orch = Orchestrator(state_dir, gate_id="gate-mcp", gate_key=gate_key, gate_did=gate_did)
    orch.add_tenant("dogfood", [agent_did])
    return McpServer(orch, "dogfood"), agent_did


def payload(response: dict) -> dict:
    text = response["result"]["content"][0]["text"]
    return json.loads(text)


class TestMcpInProcess(unittest.TestCase):
    def test_initialize_and_ping(self):
        with tempfile.TemporaryDirectory() as tmp:
            server, _ = make_server(Path(tmp))
            init = server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}})
            self.assertEqual(init["result"]["protocolVersion"], "2025-06-18")
            self.assertIn("tools", init["result"]["capabilities"])
            self.assertIsNone(server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}))
            self.assertEqual(server.handle({"jsonrpc": "2.0", "id": 2, "method": "ping"})["result"], {})

    def test_tools_list_is_the_contract_surface(self):
        with tempfile.TemporaryDirectory() as tmp:
            server, _ = make_server(Path(tmp))
            listed = server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
            names = {tool["name"] for tool in listed["result"]["tools"]}
            self.assertEqual(names, EXPECTED_TOOLS)
            self.assertEqual(names, {tool["name"] for tool in TOOLS})

    def test_full_flow_over_mcp(self):
        with tempfile.TemporaryDirectory() as tmp:
            server, agent_did = make_server(Path(tmp))
            passed = payload(
                server.handle(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/call",
                        "params": {
                            "name": "mandala.pass",
                            "arguments": {"agent": agent_did, "minutes": 30, "spend_minor": 1000},
                        },
                    }
                )
            )
            self.assertIn("token", passed)
            executed = payload(
                server.handle(
                    {
                        "jsonrpc": "2.0",
                        "id": 2,
                        "method": "tools/call",
                        "params": {
                            "name": "mandala.exec",
                            "arguments": {
                                "agent": agent_did,
                                "slot": passed["slot_id"],
                                "payload_ref": "echo mcp",
                                "token": passed["token"],
                            },
                        },
                    }
                )
            )
            self.assertEqual(executed["exit"], 0)
            settled = payload(
                server.handle(
                    {
                        "jsonrpc": "2.0",
                        "id": 3,
                        "method": "tools/call",
                        "params": {"name": "mandala.settle", "arguments": {"slot": passed["slot_id"], "rail_ref": "inv-mcp", "minor": 200}},
                    }
                )
            )
            self.assertEqual(settled["body"]["rail_ref"], "inv-mcp")
            terminated = payload(
                server.handle(
                    {
                        "jsonrpc": "2.0",
                        "id": 4,
                        "method": "tools/call",
                        "params": {"name": "mandala.terminate", "arguments": {"slot": passed["slot_id"]}},
                    }
                )
            )
            receipt = payload(
                server.handle(
                    {
                        "jsonrpc": "2.0",
                        "id": 5,
                        "method": "tools/call",
                        "params": {"name": "mandala.receipt", "arguments": {"task_id": terminated["task_id"], "verify": True}},
                    }
                )
            )
            self.assertEqual(receipt["verdict"]["verdict"], "TRUSTED", receipt["verdict"]["errors"])
            self.assertEqual(receipt["verdict"]["summary"]["receipts"], 6)

    def test_tool_errors_are_structured(self):
        with tempfile.TemporaryDirectory() as tmp:
            server, agent_did = make_server(Path(tmp))
            unknown = server.handle(
                {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "mandala.nope", "arguments": {}}}
            )
            self.assertTrue(unknown["result"]["isError"])
            self.assertEqual(payload(unknown)["error"], "unknown_tool")

            snapshot = server.handle(
                {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "mandala.snapshot", "arguments": {"slot": "slot-x"}}}
            )
            self.assertEqual(payload(snapshot)["error"], "not_found")

            unknown_agent = payload(
                server.handle(
                    {
                        "jsonrpc": "2.0",
                        "id": 3,
                        "method": "tools/call",
                        "params": {"name": "mandala.pass", "arguments": {"agent": "did:key:zNobody"}},
                    }
                )
            )
            self.assertIn("pass_id", unknown_agent)  # v0 gates by tenant, not per-agent allowlist

    def test_method_not_found(self):
        with tempfile.TemporaryDirectory() as tmp:
            server, _ = make_server(Path(tmp))
            response = server.handle({"jsonrpc": "2.0", "id": 9, "method": "resources/list"})
            self.assertEqual(response["error"]["code"], -32601)


class TestMcpSubprocess(unittest.TestCase):
    def test_stdio_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            server, agent_did = make_server(state)  # registers tenant in state.json
            proc = subprocess.Popen(
                [sys.executable, "-m", "gate_lite.mcp_server", "--state", str(state), "--tenant", "dogfood"],
                cwd=str(ROOT),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            def send(message: dict) -> dict:
                proc.stdin.write(json.dumps(message) + "\n")
                proc.stdin.flush()
                line = proc.stdout.readline()
                return json.loads(line)

            init = send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
            self.assertIn("serverInfo", init["result"])
            listed = send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
            self.assertEqual(len(listed["result"]["tools"]), len(EXPECTED_TOOLS))

            passed = payload(
                send(
                    {
                        "jsonrpc": "2.0",
                        "id": 3,
                        "method": "tools/call",
                        "params": {"name": "mandala.pass", "arguments": {"agent": agent_did}},
                    }
                )
            )
            terminated = payload(
                send(
                    {
                        "jsonrpc": "2.0",
                        "id": 4,
                        "method": "tools/call",
                        "params": {"name": "mandala.terminate", "arguments": {"slot": passed["slot_id"]}},
                    }
                )
            )
            receipt = payload(
                send(
                    {
                        "jsonrpc": "2.0",
                        "id": 5,
                        "method": "tools/call",
                        "params": {"name": "mandala.receipt", "arguments": {"task_id": terminated["task_id"], "verify": True}},
                    }
                )
            )
            self.assertIn(receipt["verdict"]["verdict"], ("TRUSTED", "PROVISIONAL"))
            proc.stdin.close()
            proc.wait(timeout=10)


if __name__ == "__main__":
    unittest.main(verbosity=2)
