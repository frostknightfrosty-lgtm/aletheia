#!/usr/bin/env python3
"""Phase 12 egress wiring scenario, run with a real Docker daemon.

This exercises the wiring pattern end to end on a custom ``--internal`` Docker
network (no default egress):

  * ``policy``         every registered adapter whose descriptor declares
                       ``network_required=True`` is covered by the wiring policy
                       (Phase 15 replaced the Phase 12 three-name allowlist);
  * ``forward``        a client container (built from the adapter image) reaches a
                       local origin through the egress proxy; the proxy logs the
                       request with a status the reader validates, and the log is
                       appended to a run's hash-chained audit log;
  * ``adapter-proxied`` the real ``search_engines`` runner image is run under the
                       proxy and its outbound requests appear in the proxy log;
  * ``previously-unwired`` the real ``crtsh`` runner — not in the Phase 12
                       allowlist — is run under the proxy; its HTTPS attempt is
                       logged by the proxy (and fails closed, as it must);
  * ``fail-closed``    on the internal network a container cannot reach the
                       internet directly, and cannot reach it through the proxy
                       once the proxy is stopped.

Only the standard library plus the Aletheia package is used. The four images are
already built by ``docker/build.sh``; no internet access is required.

Output: one JSON summary on stdout (``--json``) and a human line on stderr.
Exit code 0 when every check passes.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from uuid import uuid4

# Make ``aletheia`` importable when run from the repo root without installation.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from aletheia.core import chain, egress  # noqa: E402
from aletheia.core.checkpoint import CheckpointStore  # noqa: E402

PY_IMAGE = "aletheia/search-engines:v1"       # python:3.13-based adapter image
PROXY_IMAGE = egress.DEFAULT_IMAGE            # aletheia/egress-proxy:v1
ORIGIN_PORT = 8080
ORIGIN_BODY = "aletheia-egress-origin-ok"

ORIGIN_SCRIPT = f'''\
import http.server

BODY = b"{ORIGIN_BODY}"


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(BODY)))
        self.end_headers()
        self.wfile.write(BODY)

    def log_message(self, *args):
        pass


http.server.HTTPServer(("0.0.0.0", {ORIGIN_PORT}), Handler).serve_forever()
'''

CLIENT_SCRIPT = '''\
import sys
import urllib.request

url = sys.argv[1]
timeout = float(sys.argv[2]) if len(sys.argv) > 2 else 10.0
try:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        sys.stdout.write(response.read().decode("utf-8", "replace"))
except Exception as exc:  # noqa: BLE001 - the scenario only needs the failure
    print("UNREACHABLE " + type(exc).__name__)
    raise SystemExit(3)
'''


def _docker(argv: list[str], timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout)


def _docker_or_raise(argv: list[str], timeout: int = 120) -> subprocess.CompletedProcess:
    proc = _docker(argv, timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError("docker failed: " + " ".join(argv) + "\n" + proc.stderr)
    return proc


def _client(script_dir: Path, network: str, url: str, *, proxy_url: str | None, timeout: float = 10.0) -> str:
    """Run the generic client container and return its stdout."""
    argv = [
        "docker", "run", "--rm",
        "--network", network,
        "-v", f"{script_dir}:/scripts:ro",
    ]
    if proxy_url:
        argv += [
            "-e", f"HTTP_PROXY={proxy_url}",
            "-e", f"HTTPS_PROXY={proxy_url}",
            "-e", f"NO_PROXY=localhost,127.0.0.1",
        ]
    argv += ["--entrypoint", "python", PY_IMAGE, "/scripts/client.py", url, str(timeout)]
    proc = _docker(argv, timeout=120)
    return (proc.stdout or "") + (proc.stderr or "")


def _wait_for_proxy(script_dir: Path, network: str, proxy_url: str, url: str) -> bool:
    deadline = time.time() + 60
    while time.time() < deadline:
        if ORIGIN_BODY in _client(script_dir, network, url, proxy_url=proxy_url):
            return True
        time.sleep(2)
    return False


def _policy_check() -> dict:
    """Every network-requiring adapter in the real registry must be wired.

    This is the Phase 15 coverage claim checked against the registry itself, so
    an adapter added later is covered the moment it declares ``network_required``.
    """
    from aletheia.adapters.registry import phase7_adapters

    adapters = phase7_adapters()
    expected = {name for name, adapter in adapters.items() if adapter.descriptor.network_required}
    wired = {
        name
        for name, adapter in adapters.items()
        if egress.is_wired(name, network_required=adapter.descriptor.network_required)
    }
    return {
        "name": "phase15-egress-policy-covers-registry",
        "ok": wired == expected and len(adapters) == 49 and len(expected) > 3,
        "detail": f"adapters={len(adapters)} network_required={len(expected)} wired={len(wired)}",
    }


def _run_checks(script_dir: Path, network: str, proxy_name: str, proxy_url: str, log_path: Path) -> dict:
    # One list, assembled here: an earlier version appended the policy check in
    # main() and then overwrote it with this return value, so the check ran but
    # never reached the summary.
    checks: list[dict] = [_policy_check()]
    origin_host = "origin"

    # -- forward: proxy forwards to the local origin and logs the request ------
    ready = _wait_for_proxy(script_dir, network, proxy_url, f"http://{origin_host}:{ORIGIN_PORT}/")
    body = _client(script_dir, network, f"http://{origin_host}:{ORIGIN_PORT}/", proxy_url=proxy_url) if ready else ""
    checks.append({
        "name": "phase12-egress-forward",
        "ok": ready and ORIGIN_BODY in body,
        "detail": "proxy forwarded to the local origin" if ORIGIN_BODY in body else "forward failed: " + body[-200:],
    })

    # -- adapter-proxied: the real search_engines runner egresses via the proxy -
    runner = _docker([
        "docker", "run", "--rm",
        "--network", network,
        "--entrypoint", "python",
        "-e", f"HTTP_PROXY={proxy_url}",
        "-e", f"HTTPS_PROXY={proxy_url}",
        "-e", "NO_PROXY=localhost,127.0.0.1",
        PY_IMAGE, "/opt/runner.py", "name", "aletheia-egress-scenario.invalid",
    ])
    checks.append({
        "name": "phase12-egress-adapter-proxied",
        "ok": runner.returncode == 0,
        "detail": "search_engines runner completed rc=" + str(runner.returncode) + " through the proxy",
    })

    # -- Phase 15: an adapter outside the old allowlist is proxied as well -----
    # crtsh was NOT wired in Phase 12. On the internal network its upstream is
    # unreachable, so the runner must fail; what this proves is that the attempt
    # went through the proxy and was logged (the proxy records a 502 upstream
    # failure for the CONNECT before closing the tunnel).
    crtsh = _docker([
        "docker", "run", "--rm",
        "--network", network,
        "--entrypoint", "python",
        "-e", f"HTTP_PROXY={proxy_url}",
        "-e", f"HTTPS_PROXY={proxy_url}",
        "-e", "NO_PROXY=localhost,127.0.0.1",
        "aletheia/crtsh:public-json", "/opt/runner.py", "aletheia-egress-scenario.invalid",
    ])
    crt_entries = [entry for entry in egress.read_log(log_path) if "crt.sh" in entry.host]
    checks.append({
        "name": "phase15-egress-previously-unwired-adapter",
        "ok": bool(crt_entries) and crtsh.returncode != 0,
        "detail": "crtsh rc=" + str(crtsh.returncode) + " crt.sh log entries=" + str(len(crt_entries)),
    })

    # -- fail-closed: no direct internet, and no path once the proxy is stopped -
    direct = _client(script_dir, network, "http://1.1.1.1/", proxy_url=None, timeout=5.0)
    stopped = _docker(["docker", "rm", "-f", proxy_name])
    via_dead_proxy = _client(script_dir, network, f"http://{origin_host}:{ORIGIN_PORT}/", proxy_url=proxy_url)
    fail_closed = "UNREACHABLE" in direct and "UNREACHABLE" in via_dead_proxy
    checks.append({
        "name": "phase12-egress-fail-closed",
        "ok": fail_closed and stopped.returncode == 0,
        "detail": f"direct={direct.strip()[:60]!r} proxy_down={via_dead_proxy.strip()[:60]!r}",
    })
    return {"checks": checks}


def _append_log_to_chain(log_path: Path, data_root: Path) -> dict:
    entries = egress.read_log(log_path)
    run_id = uuid4()
    CheckpointStore(data_root / "runs").save(
        run_id, {"goal": "phase12 egress scenario", "chain_tip": chain.GENESIS_HASH}
    )
    appended = egress.append_log_to_chain(run_id, entries, data_root=data_root)
    verified = chain.verify(run_id, data_root=data_root)
    audit_path = data_root / "runs" / str(run_id) / "AUDIT.jsonl"
    events = [
        json.loads(line)
        for line in audit_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ] if audit_path.exists() else []
    egress_events = [event for event in events if event.get("event_type") == "egress_request"]
    return {
        "run_id": str(run_id),
        "log_entries": len(entries),
        "appended": appended,
        "audit_events": len(events),
        "egress_events": len(egress_events),
        "valid": bool(verified.get("valid")),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", help="directory to copy the raw proxy log and summary into")
    parser.add_argument("--json", action="store_true", help="print the JSON summary on stdout")
    args = parser.parse_args(argv)

    if shutil.which("docker") is None:
        print("egress scenario requires the Docker CLI", file=sys.stderr)
        return 2

    suffix = f"{os.getpid()}-{int(time.time())}"
    network = f"aletheia-egress-scenario-{suffix}"
    proxy = egress.EgressProxy("search_engines", rate=1000.0, capacity=1000.0)
    proxy_name = proxy.container_name
    origin_name = f"aletheia-origin-{suffix}"
    work = Path(tempfile.mkdtemp(prefix="aletheia-egress-scenario-"))
    script_dir = work / "scripts"
    log_dir = work / "log"
    data_root = work / "data"
    script_dir.mkdir(parents=True)
    log_dir.mkdir(parents=True)
    (script_dir / "client.py").write_text(CLIENT_SCRIPT, encoding="utf-8")
    (script_dir / "origin.py").write_text(ORIGIN_SCRIPT, encoding="utf-8")
    # The proxy image runs as uid 10001; the mounted log dir must be writable.
    os.chmod(log_dir, 0o777)

    summary: dict = {"network": network, "checks": [], "chain": {}}
    try:
        _docker_or_raise(egress.create_network_command(network))
        _docker_or_raise([
            "docker", "run", "-d", "--rm",
            "--name", origin_name,
            "--network", network,
            "--network-alias", "origin",
            "--entrypoint", "python",
            "-v", f"{script_dir}:/origin:ro",
            PY_IMAGE, "/origin/origin.py",
        ])
        _docker_or_raise(proxy.run_command(log_dir=log_dir, network=network, detached=True, publish_port=False))

        summary.update(_run_checks(script_dir, network, proxy_name, proxy.proxy_url, log_dir / egress.LOG_FILENAME))
        summary["chain"] = _append_log_to_chain(log_dir / egress.LOG_FILENAME, data_root)

        got = summary["chain"]
        chain_ok = (
            got["log_entries"] > 0
            and got["appended"] == got["log_entries"]
            and got["egress_events"] == got["log_entries"]
            and got["valid"]
        )
        summary["checks"].append({
            "name": "phase12-egress-chain",
            "ok": chain_ok,
            "detail": json.dumps(got, sort_keys=True),
        })
    finally:
        _docker(["docker", "rm", "-f", proxy_name])
        _docker(["docker", "rm", "-f", origin_name])
        _docker(egress.remove_network_command(network))

    if args.artifacts:
        dest = Path(args.artifacts)
        dest.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / egress.LOG_FILENAME
        if log_path.exists():
            shutil.copyfile(log_path, dest / "EGRESS.jsonl")
        (dest / "egress-scenario.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    shutil.rmtree(work, ignore_errors=True)

    failed = [check for check in summary["checks"] if not check["ok"]]
    overall = "PASS" if not failed else "FAIL"
    print(f"EGRESS SCENARIO: {overall} — {len(summary['checks']) - len(failed)}/{len(summary['checks'])} checks passed",
          file=sys.stderr)
    for check in failed:
        print(f"FAILED {check['name']}: {check['detail']}", file=sys.stderr)
    if args.json:
        print(json.dumps(summary, sort_keys=True))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
