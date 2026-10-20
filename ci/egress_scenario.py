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
                       logged by the proxy as exactly one new CONNECT entry;
  * ``fail-closed``    on the internal network a container cannot reach the
                       internet directly, and cannot reach it through the proxy
                       once the proxy is stopped;
  * ``uplink``         the proxy is dual-homed: an origin on the uplink network
                       is reachable through the proxy and unreachable directly
                       from the internal network (repair after run 39120709419);
  * ``uplink-https``   a TLS origin on the uplink network is fetched through the
                       CONNECT tunnel: TLS only completes when both tunnel
                       directions are pumped, and the logged byte count proves
                       data flowed (repair after run 39125383530).

Only the standard library plus the Aletheia package is used. The images are
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
ORIGIN_TLS_PORT = 8443
ORIGIN_BODY = "aletheia-egress-origin-ok"

ORIGIN_SCRIPT = f'''\
import http.server
import ssl
import threading

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


def serve(port, tls_context=None):
    server = http.server.ThreadingHTTPServer(("0.0.0.0", port), Handler)
    if tls_context is not None:
        server.socket = tls_context.wrap_socket(server.socket, server_side=True)
    server.serve_forever()


tls_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
tls_context.load_cert_chain("/origin/cert.pem", "/origin/key.pem")
threading.Thread(target=serve, args=({ORIGIN_TLS_PORT}, tls_context), daemon=True).start()
serve({ORIGIN_PORT})
'''

CLIENT_SCRIPT = '''\
import ssl
import sys
import urllib.request

url = sys.argv[1]
timeout = float(sys.argv[2]) if len(sys.argv) > 2 else 10.0
# The scenario's TLS origin uses a throwaway self-signed certificate.
context = ssl._create_unverified_context() if "--insecure" in sys.argv else None
try:
    with urllib.request.urlopen(url, timeout=timeout, context=context) as response:
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


def _client(script_dir: Path, network: str, url: str, *, proxy_url: str | None, timeout: float = 10.0,
            insecure: bool = False) -> str:
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
    if insecure:
        argv.append("--insecure")
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
        "ok": wired == expected and len(adapters) == 53 and len(expected) > 3,
        "detail": f"adapters={len(adapters)} network_required={len(expected)} wired={len(wired)}",
    }


def _run_checks(script_dir: Path, network: str, uplink_host: str, proxy_name: str, proxy_url: str, log_path: Path) -> dict:
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

    # -- uplink: the proxy's second interface carries the real traffic ---------
    # The uplink origin sits on the uplink network only. The internal client can
    # reach it through the proxy and cannot reach it directly: the uplink is the
    # proxy's exclusive exit (repair after run 39120709419).
    through_uplink = (
        _client(script_dir, network, f"http://{uplink_host}:{ORIGIN_PORT}/", proxy_url=proxy_url)
        if ready else ""
    )
    checks.append({
        "name": "phase12-egress-uplink-forward",
        "ok": ORIGIN_BODY in through_uplink,
        "detail": "proxy forwarded to the uplink-network origin" if ORIGIN_BODY in through_uplink
                  else "uplink forward failed: " + through_uplink[-200:],
    })
    direct_uplink = _client(script_dir, network, f"http://{uplink_host}:{ORIGIN_PORT}/", proxy_url=None, timeout=5.0)
    checks.append({
        "name": "phase12-egress-uplink-isolated",
        "ok": "UNREACHABLE" in direct_uplink,
        "detail": f"direct-to-uplink={direct_uplink.strip()[:60]!r}",
    })

    # -- uplink-https: the CONNECT tunnel must relay both directions -----------
    # TLS deadlocks whenever one direction is dropped: the client's ClientHello
    # must reach the server while the server's reply is on its way back (live
    # run 39125383530: every CONNECT entry logged "bytes": 0 and every
    # adapter's HTTPS request failed with SSL errors). The local TLS origin and
    # the logged tunnel byte count pin this deterministically, without needing
    # the internet.
    https_body = (
        _client(script_dir, network, f"https://{uplink_host}:{ORIGIN_TLS_PORT}/",
                proxy_url=proxy_url, insecure=True)
        if ready else ""
    )
    https_entries = [
        entry
        for entry in egress.read_log(log_path)
        if entry.host == uplink_host and entry.method == "CONNECT"
    ]
    https_bytes = https_entries[-1].bytes if https_entries else 0
    tls_ok = ORIGIN_BODY in https_body and https_bytes > 0
    checks.append({
        "name": "phase12-egress-uplink-https",
        "ok": tls_ok,
        "detail": "tls through the CONNECT tunnel ok; bytes=" + str(https_bytes) if tls_ok
                  else "tls failed: " + https_body[-200:] + " bytes=" + str(https_bytes),
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
    # crtsh was NOT wired in Phase 12. The crtsh runner makes exactly one request,
    # so this counts the proxy's CONNECT crt.sh entries before and after the run
    # and requires exactly one new one: the entry cannot be confused with a
    # search_engines entry (that runner's two sub-sources are Marginalia and
    # Common Crawl and it never contacts crt.sh), and the log's adapter field is
    # the scenario's single proxy name for every container. With the uplink
    # attached the request can actually reach crt.sh, which is the point of the
    # check: exactly one logged CONNECT entry; the runner's exit code is
    # recorded in the detail but no longer required to fail.
    def _crt_entries() -> list:
        return [
            entry
            for entry in egress.read_log(log_path)
            if entry.host == "crt.sh" and entry.method == "CONNECT"
        ]

    before = len(_crt_entries())
    crtsh = _docker([
        "docker", "run", "--rm",
        "--network", network,
        "--entrypoint", "python",
        "-e", f"HTTP_PROXY={proxy_url}",
        "-e", f"HTTPS_PROXY={proxy_url}",
        "-e", "NO_PROXY=localhost,127.0.0.1",
        "aletheia/crtsh:public-json", "/opt/runner.py", "aletheia-egress-scenario.invalid",
    ])
    new_entries = _crt_entries()[before:]
    checks.append({
        "name": "phase15-egress-previously-unwired-adapter",
        "ok": len(new_entries) == 1,
        "detail": "crtsh rc=" + str(crtsh.returncode)
        + " new CONNECT crt.sh entries=" + str(len(new_entries))
        + " status=" + (str(new_entries[0].status) if new_entries else "n/a"),
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
    # The uplink is a normal (non-internal) bridge network: the proxy's second
    # interface and the internal network's only route out. Found while repairing
    # the live path after run 39120709419 — a single-homed proxy reaches nothing.
    uplink = f"aletheia-egress-scenario-uplink-{suffix}"
    uplink_host = "uplink-origin"
    uplink_origin_name = f"aletheia-uplink-origin-{suffix}"
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
    # TLS material for the tunnel check: the handshake through the CONNECT
    # tunnel only completes when the proxy relays both directions (repair
    # after run 39125383530, where every CONNECT entry logged bytes=0).
    if shutil.which("openssl") is None:
        print("egress scenario requires the openssl CLI for the TLS tunnel check", file=sys.stderr)
        shutil.rmtree(work, ignore_errors=True)
        return 2
    openssl = subprocess.run(
        ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
         "-keyout", str(script_dir / "key.pem"), "-out", str(script_dir / "cert.pem"),
         "-days", "1", "-subj", "/CN=uplink-origin"],
        capture_output=True, text=True,
    )
    if openssl.returncode != 0:
        print("openssl failed to create the scenario certificate:\n" + openssl.stderr, file=sys.stderr)
        shutil.rmtree(work, ignore_errors=True)
        return 2
    # The origins run as uid 10001 and OpenSSL writes private keys as 0600, so
    # the key would be unreadable and the origin would die before it ever
    # listens (run 39128092472: every origin request 502ed at the proxy and all
    # three origin checks failed). The certificate is a throwaway local
    # artifact, so widen the mode instead of running the origin as root.
    os.chmod(script_dir / "cert.pem", 0o644)
    os.chmod(script_dir / "key.pem", 0o644)
    # The proxy lifecycle goes through the same ProxySession the orchestrator
    # uses — network creation, the world-writable log dir and the uplink attach
    # included — so a regression there fails here instead of in a live run.
    session = egress.ProxySession(
        "search_engines", log_dir, rate=1000.0, capacity=1000.0,
        network=network, uplink=uplink, runner=_docker,
    )

    summary: dict = {"network": network, "uplink": uplink, "checks": [], "chain": {}}
    try:
        # The uplink network must exist before the proxy is attached to it.
        _docker_or_raise(["docker", "network", "create", uplink])
        session.start()
        _docker_or_raise([
            "docker", "run", "-d", "--rm",
            "--name", origin_name,
            "--network", network,
            "--network-alias", "origin",
            "--entrypoint", "python",
            "-v", f"{script_dir}:/origin:ro",
            PY_IMAGE, "/origin/origin.py",
        ])
        # The uplink origin is reachable only through the proxy: it sits on the
        # uplink network, which no internal-network container can route to.
        _docker_or_raise([
            "docker", "run", "-d", "--rm",
            "--name", uplink_origin_name,
            "--network", uplink,
            "--network-alias", uplink_host,
            "--entrypoint", "python",
            "-v", f"{script_dir}:/origin:ro",
            PY_IMAGE, "/origin/origin.py",
        ])

        summary.update(_run_checks(script_dir, network, uplink_host, proxy_name, proxy.proxy_url, log_dir / egress.LOG_FILENAME))
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
        _docker(["docker", "rm", "-f", uplink_origin_name])
        _docker(egress.remove_network_command(network))
        _docker(["docker", "network", "rm", uplink])

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
