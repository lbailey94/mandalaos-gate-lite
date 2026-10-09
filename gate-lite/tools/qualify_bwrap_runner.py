#!/usr/bin/env python3
"""Bounded fixed-payload Bubblewrap probe; never assigns a receipt class.

The only payload is FIXED_PROBE below. A passing result is candidate evidence
only: classification and independent-host adoption remain open. Outbound
network denial is not tested by this probe.

Example:
  python3 tools/qualify_bwrap_runner.py --expected-bwrap-sha256 sha256:<digest>
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

SCHEMA = "mandala-bwrap-probe-v1"
DEFAULT_WRAPPER = "/home/lucas/.local/bin/mandala-sandbox"
DEFAULT_WRAPPER_SHA256 = "sha256:de273c62ae22147634164e84cc9b6f6ae83a7f25e05755b50bc7c1257f525641"

FIXED_PROBE = r'''import json, os, pathlib, tempfile
def mount_info(path):
    for line in pathlib.Path("/proc/self/mountinfo").read_text().splitlines():
        before, after = line.split(" - ", 1)
        fields = before.split()
        target = fields[4].replace("\\040", " ")
        if target == path:
            return {"mountpoint": target, "options": fields[5].split(","),
                    "filesystem": after.split()[0]}
    return None
host_net = int(os.environ["QUALIFY_HOST_NET_NS_INO"])
host_mnt = int(os.environ["QUALIFY_HOST_MNT_NS_INO"])
net_ino = os.stat("/proc/self/ns/net").st_ino
mnt_ino = os.stat("/proc/self/ns/mnt").st_ino
workspace_mount = mount_info("/workspace")
tmp_mount = mount_info("/tmp")
write_denied = False
try:
    with open("/workspace/.mandala-qualification-write-probe", "xb") as f:
        f.write(b"probe")
except OSError:
    write_denied = True
tmp_write = False
try:
    fd, name = tempfile.mkstemp(prefix="mandala-qualification-")
    os.close(fd)
    os.unlink(name)
    tmp_write = True
except OSError:
    pass
print(json.dumps({"net_namespace_isolated": net_ino != host_net,
 "mount_namespace_isolated": mnt_ino != host_mnt, "workspace_mount": workspace_mount,
 "workspace_write_denied": write_denied, "tmp_mount": tmp_mount,
 "tmp_write_succeeded": tmp_write}, sort_keys=True))
'''
FIXED_PROBE_ARG = "exec(__import__('base64').b64decode(" + repr(
    base64.b64encode(FIXED_PROBE.encode("utf-8")).decode("ascii")
) + "))"


class ProbeError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def identify(path: Path) -> dict:
    resolved = path.expanduser().resolve(strict=True)
    if not resolved.is_file():
        raise ProbeError(f"not a regular file: {resolved}")
    return {"path": str(resolved), "sha256": sha256_file(resolved)}


def _shim_source() -> str:
    # Capture precisely the wrapper's argument tokens, then forward that same
    # vector to the resolved real executable (preserving argv[0] == "bwrap").
    return '''#!/usr/bin/python3
import json, os, sys
args = sys.argv[1:]
with open(os.environ["QUALIFY_ARGV_LOG"], "w", encoding="utf-8") as f:
    json.dump({"argv0": "bwrap", "argv": args}, f, sort_keys=True)
    f.write("\\n")
real = os.environ.pop("QUALIFY_REAL_BWRAP")
os.environ.pop("QUALIFY_ARGV_LOG", None)
os.execv(real, ["bwrap", *args])
'''


def _has_adjacent(argv: list[str], flag: str, first: str, second: str | None = None) -> bool:
    width = 3 if second is not None else 2
    expected = [flag, first] + ([second] if second is not None else [])
    return any(argv[i:i + width] == expected for i in range(len(argv) - width + 1))


def _empty_evidence(wrapper_path: str, expected_wrapper_sha256: str | None) -> dict:
    return {
        "schema": SCHEMA,
        "conclusion": "OPEN",
        "classification_status": "OPEN",
        "probe_status": "NOT_RUN",
        "wrapper": {"configured_path": wrapper_path, "expected_sha256": expected_wrapper_sha256},
        "bwrap": {},
        "invocation": {},
        "probes": {},
        "limitations": [
            "A passing same-host probe does not assign a receipt sandbox_class or close classification/adoption.",
            "The namespace comparison does not prove outbound network denial to every destination.",
            "This is not independent-host adoption evidence.",
            "This fixed probe uses a one-line encoded Python trampoline and does not itself qualify newline-containing payload arguments; run the wrapper argv tests separately.",
        ],
    }


def qualify(
    wrapper_path: str = DEFAULT_WRAPPER,
    *,
    expected_wrapper_sha256: str | None = DEFAULT_WRAPPER_SHA256,
    expected_bwrap_sha256: str | None = None,
    bwrap_path: str | None = None,
    timeout_s: float = 20.0,
) -> dict:
    """Run only FIXED_PROBE and return evidence, including failures."""
    evidence = _empty_evidence(wrapper_path, expected_wrapper_sha256)
    try:
        wrapper = identify(Path(wrapper_path))
        evidence["wrapper"].update(wrapper)
        if expected_wrapper_sha256 and wrapper["sha256"] != expected_wrapper_sha256:
            raise ProbeError("wrapper digest does not match expected digest")

        selected = bwrap_path or shutil.which("bwrap")
        if not selected:
            raise ProbeError("bwrap executable not found on PATH")
        bwrap = identify(Path(selected))
        evidence["bwrap"].update(bwrap)
        evidence["bwrap"]["expected_sha256"] = expected_bwrap_sha256
        evidence["bwrap"]["digest_pinned"] = bool(expected_bwrap_sha256)
        if expected_bwrap_sha256 and bwrap["sha256"] != expected_bwrap_sha256:
            raise ProbeError("bwrap digest does not match expected digest")
        version = subprocess.run(
            [bwrap["path"], "--version"], capture_output=True, text=True,
            timeout=timeout_s, check=False,
        )
        evidence["bwrap"].update({
            "version_argv": [bwrap["path"], "--version"],
            "version_exit_code": version.returncode,
            "version_output": (version.stdout + version.stderr).strip()[:1000],
        })
        if version.returncode:
            raise ProbeError("resolved bwrap --version failed")

        wrapper_resolved, bwrap_resolved = Path(wrapper["path"]), Path(bwrap["path"])
        with tempfile.TemporaryDirectory(prefix="mandala-bwrap-qualify-") as tmp_name:
            tmp = Path(tmp_name)
            workspace = tmp / "workspace"
            workspace.mkdir()
            shim_dir = tmp / "bin"
            shim_dir.mkdir()
            log_path = tmp / "bwrap-argv.json"
            shim = shim_dir / "bwrap"
            shim.write_text(_shim_source(), encoding="utf-8")
            shim.chmod(0o700)
            envelope = {
                "schema": "wm-sandbox-exec-v1", "program": "/usr/bin/python3",
                "args": ["-c", FIXED_PROBE_ARG], "net": False,
                "workspace": str(workspace), "rw": False,
            }
            invocation = [str(wrapper_resolved), "--exec", json.dumps(envelope, separators=(",", ":"))]
            env = os.environ.copy()
            env["PATH"] = str(shim_dir) + os.pathsep + env.get("PATH", os.defpath)
            env["QUALIFY_ARGV_LOG"] = str(log_path)
            env["QUALIFY_REAL_BWRAP"] = str(bwrap_resolved)
            env["QUALIFY_HOST_NET_NS_INO"] = str(Path("/proc/self/ns/net").stat().st_ino)
            env["QUALIFY_HOST_MNT_NS_INO"] = str(Path("/proc/self/ns/mnt").stat().st_ino)
            evidence["invocation"] = {
                "argv": invocation,
                "payload_program": envelope["program"],
                "payload_is_fixed_probe": True,
                "payload_probe_sha256": "sha256:" + hashlib.sha256(FIXED_PROBE.encode("utf-8")).hexdigest(),
                "network_requested": False,
                "workspace_host_path": str(workspace),
                "workspace_requested_writable": False,
                "argv_capture": "temporary PATH shim forwards recorded arguments to pinned bwrap executable",
            }
            result = subprocess.run(invocation, env=env, capture_output=True, text=True,
                                     timeout=timeout_s, check=False)
            evidence["invocation"].update({
                "exit_code": result.returncode,
                "stderr": result.stderr[-4000:],
            })
            if not log_path.exists():
                raise ProbeError("wrapper did not invoke instrumented bwrap")
            captured_argv = json.loads(log_path.read_text(encoding="utf-8"))
            if not isinstance(captured_argv, dict) or not isinstance(captured_argv.get("argv"), list):
                raise ProbeError("instrumented bwrap argv record has invalid shape")
            evidence["invocation"]["bwrap_argv"] = captured_argv
            try:
                observed = json.loads(result.stdout)
            except json.JSONDecodeError as exc:
                raise ProbeError("fixed in-sandbox probe did not emit JSON") from exc
            if not isinstance(observed, dict):
                raise ProbeError("fixed in-sandbox probe result is not an object")
            evidence["probes"]["observed"] = observed
            args = captured_argv.get("argv", [])
            workspace_mount = observed.get("workspace_mount") or {}
            tmp_mount = observed.get("tmp_mount") or {}
            checks = {
                "unshare_all_requested": "--unshare-all" in args,
                "readonly_workspace_bind_requested": _has_adjacent(args, "--ro-bind", str(workspace), "/workspace"),
                "tmpfs_tmp_requested": _has_adjacent(args, "--tmpfs", "/tmp"),
                "die_with_parent_requested": "--die-with-parent" in args,
                "runner_exit_zero": result.returncode == 0,
                "network_namespace_isolated": observed.get("net_namespace_isolated") is True,
                "mount_namespace_isolated": observed.get("mount_namespace_isolated") is True,
                "workspace_mount_readonly": "ro" in workspace_mount.get("options", []),
                "workspace_write_denied": observed.get("workspace_write_denied") is True,
                "tmp_is_tmpfs": tmp_mount.get("filesystem") == "tmpfs",
                "tmp_write_succeeded": observed.get("tmp_write_succeeded") is True,
            }
            evidence["probes"].update({
                "checks": checks,
                "status": "PASS" if all(checks.values()) else "FAIL",
                "outbound_egress_denial_tested": False,
            })
            if wrapper_resolved.resolve(strict=True) != wrapper_resolved or sha256_file(wrapper_resolved) != wrapper["sha256"]:
                raise ProbeError("wrapper identity changed during probe")
            if bwrap_resolved.resolve(strict=True) != bwrap_resolved or sha256_file(bwrap_resolved) != bwrap["sha256"]:
                raise ProbeError("bwrap identity changed during probe")
            evidence["identity_stable_after_probe"] = True
            evidence["probe_status"] = evidence["probes"]["status"]
            return evidence
    except (OSError, ProbeError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        evidence["probe_status"] = "FAIL"
        evidence["failure"] = str(exc)
        evidence["identity_stable_after_probe"] = False
        evidence.setdefault("probes", {}).setdefault("status", "FAIL")
        return evidence


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wrapper", default=DEFAULT_WRAPPER)
    parser.add_argument("--expected-wrapper-sha256", default=DEFAULT_WRAPPER_SHA256)
    parser.add_argument("--bwrap", default=None, help="resolved executable path; defaults to PATH lookup")
    parser.add_argument("--expected-bwrap-sha256", default=None)
    parser.add_argument("--timeout", type=float, default=20.0)
    args = parser.parse_args(argv)
    evidence = qualify(
        args.wrapper, expected_wrapper_sha256=args.expected_wrapper_sha256,
        expected_bwrap_sha256=args.expected_bwrap_sha256, bwrap_path=args.bwrap,
        timeout_s=args.timeout,
    )
    print(json.dumps(evidence, indent=2, sort_keys=True))
    return 0 if evidence.get("probe_status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
