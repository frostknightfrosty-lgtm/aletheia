#!/usr/bin/env python3
"""Execute the 32 Docker integration smoke cases and preserve raw stdout/stderr."""
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
    ("phase7-core-import", "aletheia/core:0.7.0", ["-c", "import aletheia; print('core import ok')"]),
]

def main() -> int:
    out = Path("ci-artifacts/docker-integration")
    out.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory() as td:
        sample = Path(td) / "sample.txt"
        sample.write_text("Aletheia", encoding="utf-8")
        results = []
        for name, image, args in CASES:
            cmd = ["docker", "run", "--rm", "--network", "none"]
            if name == "phase1-exiftool":
                cmd += ["-v", f"{sample}:/work/sample.txt:ro"]
            if name == "phase7-core-import":
                cmd += ["--entrypoint", "python"]
            if name == "phase4-holehe":
                cmd += ["--entrypoint", "python"]
            cmd += [image, *args]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            (out / f"{name}.stdout").write_text(proc.stdout, encoding="utf-8")
            (out / f"{name}.stderr").write_text(proc.stderr, encoding="utf-8")
            results.append({"name": name, "image": image, "command": cmd, "returncode": proc.returncode})
        (out / "results.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    failed = [r for r in results if r["returncode"] != 0]
    print(f"DOCKER CAPTURE: {'PASS' if not failed else 'FAIL'} — {len(results) - len(failed)}/{len(results)} cases captured")
    for r in failed:
        print(f"FAILED {r['name']} rc={r['returncode']}")
    return 1 if failed else 0

if __name__ == "__main__":
    sys.exit(main())
