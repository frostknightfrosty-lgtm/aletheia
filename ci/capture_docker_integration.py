#!/usr/bin/env python3
"""Execute Docker integration smoke cases and preserve raw stdout/stderr."""
from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

CASES = [
    ("phase1-sherlock", "aletheia/sherlock:0.16.2", ["--version"]),
    ("phase1-theharvester", "aletheia/theharvester:4.11.1", ["-h"]),
    ("phase1-exiftool", "aletheia/exiftool:13.59", ["-j", "/work/sample.txt"]),
    ("phase3-amass", "aletheia/amass:5.1.1", ["-version"]),
    ("phase3-subfinder", "aletheia/subfinder:2.17.0", ["-version"]),
    ("phase3-assetfinder", "aletheia/assetfinder:0.1.1", ["--help"]),
    ("phase3-dnsx", "aletheia/dnsx:1.3.1", ["-version"]),
    ("phase3-massdns", "aletheia/massdns:1.1.0", ["--help"]),
    ("phase3-dnsrecon", "aletheia/dnsrecon:1.6.3", ["--help"]),
    ("phase3-fierce", "aletheia/fierce:1.6.0", ["--help"]),
    ("phase3-shodan", "aletheia/shodan:1.31.0", ["--health"]),
    ("phase3-crtsh", "aletheia/crtsh:public-json", ["--health"]),
    ("phase4-maigret", "aletheia/maigret:0.6.6", ["--version"]),
    ("phase4-holehe", "aletheia/holehe:1.61", ["-c", "from holehe.core import __version__; print(__version__)"]),
    ("phase4-h8mail", "aletheia/h8mail:2.5.6", ["--help"]),
    ("phase4-hibp", "aletheia/hibp:api-v3", ["--health"]),
    ("phase4-xposedornot", "aletheia/xposedornot:api-v1", ["--health"]),
    ("phase4-phoneinfoga", "aletheia/phoneinfoga:2.11.0", ["version"]),
    ("phase4-libphonenumber", "aletheia/libphonenumber:9.0.40", ["--health"]),
    ("phase5-instaloader", "aletheia/instaloader:4.15.3", ["--health"]),
    ("phase5-reddit", "aletheia/reddit-api:v1", ["--health"]),
    ("phase5-youtube", "aletheia/youtube-api:v3", ["--health"]),
    ("phase5-overpass", "aletheia/overpass:public", ["--health"]),
    ("phase5-suncalc", "aletheia/suncalc:2.0.2", ["--health"]),
    ("phase5-deepface", "aletheia/deepface:0.0.101", ["--health"]),
    ("phase5-insightface", "aletheia/insightface:2.1", ["--health"]),
    ("phase6-sec-edgar", "aletheia/sec-edgar:public-api", ["--health"]),
    ("phase6-gleif", "aletheia/gleif:api-v1", ["--health"]),
    ("phase6-opencorporates", "aletheia/opencorporates:api-v0.4.8", ["--health"]),
    ("phase6-opensanctions", "aletheia/opensanctions:api", ["--health"]),
    ("phase6-courtlistener", "aletheia/courtlistener:api-v3", ["--health"]),
    ("phase7-core-import", "aletheia/core:0.7.0", ["-c", "from fastapi.testclient import TestClient; from aletheia.api.app import app; response = TestClient(app).get('/'); assert response.status_code == 200, response.text; print('core API ok')"]),
    ("phase5c-gravatar", "aletheia/gravatar:api-v3", ["--health"]),
    ("phase5c-rdap", "aletheia/rdap:rfc9082", ["--health"]),
    ("phase9-ip-intelligence", "aletheia/ip-intelligence:v1", ["--health"]),
    ("phase9-gov-records-us", "aletheia/gov-records-us:v1", ["--health"]),
    ("phase9-corp-registry", "aletheia/corp-registry:v1", ["--health"]),
    ("phase9-sanctions-watchlists", "aletheia/sanctions-watchlists:v1", ["--health"]),
    ("phase9-academic-search", "aletheia/academic-search:v1", ["--health"]),
    ("phase9-ssl-tls", "aletheia/ssl-tls:v1", ["--health"]),
    ("phase17-ssl-tls-cipherscan", "aletheia/ssl-tls:v1", ["--selftest-cipherscan"]),
    ("phase17-leak-checkers-bron-vault", "aletheia/leak-checkers:v1", ["--selftest-bron-vault"]),
    ("phase9-crypto-blockchain", "aletheia/crypto-blockchain:v1", ["--health"]),
    ("phase9-patents-trademarks", "aletheia/patents-trademarks:v1", ["--health"]),
    ("phase9-email-auth", "aletheia/email-auth:v1", ["--health"]),
    ("phase9-code-search", "aletheia/code-search:v1", ["--health"]),
    ("phase9-search-engines", "aletheia/search-engines:v1", ["--health"]),
    ("phase17-search-engines-searxng", "aletheia/search-engines:v1", ["--selftest-searxng"]),
    ("phase9-geolocation-image", "aletheia/geolocation-image:v1", ["--health"]),
    ("phase9-transport-asset-registry", "aletheia/transport-asset-registry:v1", ["--health"]),
    ("phase9-social-profile", "aletheia/social-profile:v1", ["--health"]),
    ("phase9-social-username", "aletheia/social-username:v1", ["--health"]),
    ("phase9-leak-checkers", "aletheia/leak-checkers:v1", ["--health"]),
    ("phase17-zehef-health", "aletheia/zehef:v1", ["--health"]),
    ("phase17-zehef-selftest", "aletheia/zehef:v1", ["--selftest"]),
    ("phase17-tiktok-hashtag-health", "aletheia/tiktok-hashtag:v1", ["--health"]),
    ("phase17-tiktok-hashtag-selftest", "aletheia/tiktok-hashtag:v1", ["--selftest"]),
    ("phase17-venom-health", "aletheia/venom:v1", ["--health"]),
    ("phase17-venom-selftest", "aletheia/venom:v1", ["--selftest"]),
    ("phase17-picimagesearch-health", "aletheia/picimagesearch:v1", ["--health"]),
    ("phase17-picimagesearch-selftest", "aletheia/picimagesearch:v1", ["--selftest"]),
    ("phase17-tracelines-health", "aletheia/tracelines:v1", ["--health"]),
    ("phase17-tracelines-selftest", "aletheia/tracelines:v1", ["--selftest"]),
    ("phase17-shadowfinder-health", "aletheia/shadowfinder:v1", ["--health"]),
    ("phase17-shadowfinder-selftest", "aletheia/shadowfinder:v1", ["--selftest"]),
    ("phase17-pybdshadow-health", "aletheia/pybdshadow:v1", ["--health"]),
    ("phase17-pybdshadow-selftest", "aletheia/pybdshadow:v1", ["--selftest"]),
    ("phase17-pybdshadow-run", "aletheia/pybdshadow:v1", ["/work/input.json"]),
    ("phase17-crypttrace-health", "aletheia/crypttrace:v1", ["--health"]),
    ("phase17-crypttrace-selftest", "aletheia/crypttrace:v1", ["--selftest"]),
    ("phase17-crypttrace-normalize", "aletheia/crypttrace:v1", ["--normalize", "/work/report.json"]),
    ("phase17-researcher-ids-health", "aletheia/researcher-ids:v1", ["--health"]),
    ("phase17-researcher-ids-selftest", "aletheia/researcher-ids:v1", ["--selftest"]),
    ("phase17-researcher-ids-normalize", "aletheia/researcher-ids:v1", ["--normalize", "/work/combined.json"]),
    ("phase17-weather-health", "aletheia/weather:v1", ["--health"]),
    ("phase17-weather-selftest", "aletheia/weather:v1", ["--selftest"]),
    ("phase17-weather-normalize", "aletheia/weather:v1", ["--normalize", "/work/response.json"]),
    ("phase17-github-identity-health", "aletheia/github-identity:v1", ["--health"]),
    ("phase17-github-identity-selftest", "aletheia/github-identity:v1", ["--selftest"]),
    ("phase17-github-identity-normalize", "aletheia/github-identity:v1", ["--normalize", "/work/combined.json"]),
    ("phase17-pgp-keys-health", "aletheia/pgp-keys:v1", ["--health"]),
    ("phase17-pgp-keys-selftest", "aletheia/pgp-keys:v1", ["--selftest"]),
    ("phase17-pgp-keys-normalize", "aletheia/pgp-keys:v1", ["--normalize", "/work/combined.json"]),
    ("phase17-minecraft-health", "aletheia/minecraft:v1", ["--health"]),
    ("phase17-minecraft-selftest", "aletheia/minecraft:v1", ["--selftest"]),
    ("phase17-minecraft-normalize", "aletheia/minecraft:v1", ["--normalize", "/work/profile.json"]),
    ("phase18-spiderfoot-health", "aletheia/spiderfoot:v4.0", ["--health"]),
    ("phase11-egress-proxy", "aletheia/egress-proxy:v1", ["--health"]),
]

def _scenario_results(out: Path) -> list:
    """Run the Phase 12 wiring scenario and turn its checks into capture cases."""
    proc = subprocess.run(
        [sys.executable, "ci/egress_scenario.py", "--json", "--artifacts", str(out)],
        capture_output=True, text=True, timeout=1200,
    )
    lines = [line for line in proc.stdout.splitlines() if line.strip().startswith("{")]
    checks = []
    if lines:
        try:
            checks = json.loads(lines[-1]).get("checks", [])
        except json.JSONDecodeError:
            checks = []
    if not checks:
        return [{
            "name": "phase12-egress-scenario",
            "image": "aletheia/egress-proxy:v1",
            "command": ["scenario", "phase12"],
            "returncode": proc.returncode or 1,
            "scenario": True,
            "detail": (proc.stderr or "")[-500:],
        }]
    return [
        {
            "name": check["name"],
            "image": "aletheia/egress-proxy:v1",
            "command": ["scenario", check["name"]],
            "returncode": 0 if check["ok"] else 1,
            "scenario": True,
            "detail": check.get("detail", ""),
        }
        for check in checks
    ]


def main() -> int:
    out = Path("ci-artifacts/docker-integration")
    out.mkdir(parents=True, exist_ok=True)
    results = []
    with TemporaryDirectory() as td:
        sample = Path(td) / "sample.txt"
        sample.write_text("Aletheia", encoding="utf-8")
        pybdshadow_input = Path(td) / "buildings.json"
        pybdshadow_input.write_text(json.dumps({
            "datetime_utc": "2024-06-01T12:00:00Z",
            "buildings": {
                "type": "FeatureCollection",
                "features": [{
                    "type": "Feature",
                    "properties": {"building_id": "capture-b1", "height": 10.0},
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[
                            [0.0, 0.0], [0.0002, 0.0], [0.0002, 0.0002],
                            [0.0, 0.0002], [0.0, 0.0],
                        ]],
                    },
                }],
            },
        }), encoding="utf-8")
        crypttrace_report = Path(td) / "report.json"
        crypttrace_report.write_text(json.dumps({
            "tool": "crypttrace v0.22.0",
            "generated": "2026-01-01 12:00 UTC",
            "subject": "bc1qar0srrr7xfkvy5l643lydnw9re59gtzzwf5mdq",
            "chain": "btc",
            "traced_asset": "BTC",
            "trace_depth": 2,
            "trace_branching": 3,
            "data_source": "mempool.space",
            "summary": {
                "balance_native": 0.125, "native_symbol": "BTC",
                "transfers_analysed": 4, "first_seen": "2026-01-01 10:00",
                "last_seen": "2026-01-01 11:00", "label": None,
                "type": "unknown", "risk_score": 0,
            },
            "assessment": {
                "assessment": "No labelled entities were reached within the traced depth.",
                "risk": 0, "confidence": "low",
            },
            "key_findings": [{
                "address": "bc1qar0srrr7xfkvy5l643lydnw9re59gtzzwf5mdq",
                "label": "Example exchange", "type": "exchange", "risk": 70,
                "value_reached": 0.01, "symbol": "BTC", "usd_reached": 1000.0,
                "memo": None,
            }],
            "top_counterparties": [{
                "address": "bc1qar0srrr7xfkvy5l643lydnw9re59gtzzwf5mdq",
                "label": "Example exchange", "in": 0.0, "out": 0.01, "txs": 1,
            }],
            "errors": [],
        }), encoding="utf-8")
        researcher_ids_combined = Path(td) / "combined.json"
        researcher_ids_combined.write_text(
            Path("tests/fixtures/researcher_ids.json").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        weather_response = Path(td) / "weather.json"
        weather_response.write_text(json.dumps({
            "latitude": 51.49349, "longitude": -0.13172913,
            "utc_offset_seconds": 0, "timezone": "GMT", "elevation": 8.0,
            "current_units": {"time": "iso8601", "temperature_2m": "°C",
                              "precipitation": "mm", "weather_code": "wmo code"},
            "current": {"time": "2026-10-20T19:30", "interval": 900,
                        "temperature_2m": 12.0, "precipitation": 0.0,
                        "weather_code": 3, "wind_speed_10m": 10.8},
        }), encoding="utf-8")
        github_identity_combined = Path(td) / "github_identity.json"
        github_identity_combined.write_text(
            Path("tests/fixtures/github_identity.json").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        pgp_keys_combined = Path(td) / "pgp_keys.json"
        pgp_keys_combined.write_text(
            Path("tests/fixtures/pgp_keys.json").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        minecraft_profile = Path(td) / "minecraft.json"
        minecraft_profile.write_text(
            Path("tests/fixtures/minecraft.json").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        for name, image, args in CASES:
            cmd = ["docker", "run", "--rm", "--network", "none"]
            if name == "phase1-exiftool":
                cmd += ["-v", f"{sample}:/work/sample.txt:ro"]
            if name == "phase17-pybdshadow-run":
                cmd += ["-v", f"{pybdshadow_input}:/work/input.json:ro"]
            if name == "phase17-crypttrace-normalize":
                cmd += ["-v", f"{crypttrace_report}:/work/report.json:ro"]
            if name == "phase17-researcher-ids-normalize":
                cmd += ["-v", f"{researcher_ids_combined}:/work/combined.json:ro"]
            if name == "phase17-weather-normalize":
                cmd += ["-v", f"{weather_response}:/work/response.json:ro"]
            if name == "phase17-github-identity-normalize":
                cmd += ["-v", f"{github_identity_combined}:/work/combined.json:ro"]
            if name == "phase17-pgp-keys-normalize":
                cmd += ["-v", f"{pgp_keys_combined}:/work/combined.json:ro"]
            if name == "phase17-minecraft-normalize":
                cmd += ["-v", f"{minecraft_profile}:/work/profile.json:ro"]
            if name == "phase7-core-import":
                cmd += ["--entrypoint", "python"]
            if name == "phase4-holehe":
                cmd += ["--entrypoint", "python"]
            cmd += [image, *args]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            (out / f"{name}.stdout").write_text(proc.stdout, encoding="utf-8")
            (out / f"{name}.stderr").write_text(proc.stderr, encoding="utf-8")
            results.append({"name": name, "image": image, "command": cmd, "returncode": proc.returncode})
    results.extend(_scenario_results(out))
    (out / "results.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    failed = [r for r in results if r["returncode"] != 0]
    print(f"DOCKER CAPTURE: {'PASS' if not failed else 'FAIL'} — {len(results) - len(failed)}/{len(results)} cases captured")
    for r in failed:
        print(f"FAILED {r['name']} rc={r['returncode']}")
    return 1 if failed else 0

if __name__ == "__main__":
    sys.exit(main())
