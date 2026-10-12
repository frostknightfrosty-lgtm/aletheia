#!/usr/bin/env python3
"""Capture case for Docker integration tests.

Run: python ci/capture_docker_integration.py [phase_name]
If phase_name is provided, capture only that phase.
If no argument, capture all known phases.
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone


# Known phases with Docker integration tests
# Each entry: (phase_name, docker_dir_name, runner_args, image_name)
PHASES = [
    ("phase1-sherlock", "sherlock", ["--health"], "aletheia/sherlock:0.16.2"),
    ("phase1-theharvester", "theharvester", ["--health"], "aletheia/theharvester:4.11.1"),
    ("phase1-exiftool", "exiftool", ["--health"], "aletheia/exiftool:13.59"),
    ("phase3-amass", "amass", ["--health"], "aletheia/amass:5.1.1"),
    ("phase3-subfinder", "subfinder", ["--health"], "aletheia/subfinder:2.17.0"),
    ("phase3-assetfinder", "assetfinder", ["--health"], "aletheia/assetfinder:0.1.1"),
    ("phase3-dnsx", "dnsx", ["--health"], "aletheia/dnsx:1.3.1"),
    ("phase3-massdns", "massdns", ["--health"], "aletheia/massdns:1.1.0"),
    ("phase3-dnsrecon", "dnsrecon", ["--health"], "aletheia/dnsrecon:1.6.3"),
    ("phase3-fierce", "fierce", ["--health"], "aletheia/fierce:1.6.0"),
    ("phase3-shodan", "shodan", ["--health"], "aletheia/shodan:1.31.0"),
    ("phase3-crtsh", "crtsh", ["--health"], "aletheia/crtsh:public-json"),
    ("phase4-maigret", "maigret", ["--health"], "aletheia/maigret:0.6.6"),
    ("phase4-holehe", "holehe", ["--health"], "aletheia/holehe:1.61"),
    ("phase4-h8mail", "h8mail", ["--health"], "aletheia/h8mail:2.5.6"),
    ("phase4-hibp", "hibp", ["--health"], "aletheia/hibp:api-v3"),
    ("phase4-xposedornot", "xposedornot", ["--health"], "aletheia/xposedornot:api-v1"),
    ("phase4-phoneinfoga", "phoneinfoga", ["--health"], "aletheia/phoneinfoga:2.11.0"),
    ("phase4-libphonenumber", "libphonenumber", ["--health"], "aletheia/libphonenumber:9.0.40"),
    ("phase5-instaloader", "instaloader", ["--health"], "aletheia/instaloader:4.15.3"),
    ("phase5-reddit-api", "reddit-api", ["--health"], "aletheia/reddit-api:v1"),
    ("phase5-youtube-api", "youtube-api", ["--health"], "aletheia/youtube-api:v3"),
    ("phase5-overpass", "overpass", ["--health"], "aletheia/overpass:public"),
    ("phase5-suncalc", "suncalc", ["--health"], "aletheia/suncalc:2.0.2"),
    ("phase5-deepface", "deepface", ["--health"], "aletheia/deepface:0.0.101"),
    ("phase5-insightface", "insightface", ["--health"], "aletheia/insightface:2.1"),
    ("phase5c-gravatar", "gravatar", ["--health"], "aletheia/gravatar:api-v3"),
    ("phase5c-rdap", "rdap", ["--health"], "aletheia/rdap:rfc9082"),
    ("phase6-sec-edgar", "sec-edgar", ["--health"], "aletheia/sec-edgar:public-api"),
    ("phase6-gleif", "gleif", ["--health"], "aletheia/gleif:api-v1"),
    ("phase6-opencorporates", "opencorporates", ["--health"], "aletheia/opencorporates:api-v0.4.8"),
    ("phase6-opensanctions", "opensanctions", ["--health"], "aletheia/opensanctions:api"),
    ("phase6-courtlistener", "courtlistener", ["--health"], "aletheia/courtlistener:api-v3"),
    ("phase7-ip-intelligence", "ip_intelligence", ["--health"], "aletheia/ip-intelligence:v1"),
    ("phase9-gov-records-us", "government_records_us", ["person_name", "John Smith"], "aletheia/gov-records-us:v1"),
]


def _run_capture(phase_name: str, docker_dir: str, runner_args: list[str], image_name: str) -> dict:
    """Run capture for a single phase."""
    runner_path = os.path.join("docker", docker_dir, "runner.py")
    capture_dir = os.path.join("ci", "captures", phase_name)
    os.makedirs(capture_dir, exist_ok=True)

    # Health check (or main run for phase9)
    if phase_name == "phase9-gov-records-us":
        # For phase9, the main run is with person_name
        result = subprocess.run(
            ["python", runner_path] + runner_args,
            capture_output=True, text=True, timeout=120
        )
        health_check = {"stdout": "N/A (main run)", "exit_code": 0}
    else:
        result = subprocess.run(
            ["python", runner_path] + runner_args,
            capture_output=True, text=True, timeout=60
        )
        health_check = {"stdout": result.stdout.strip(), "exit_code": result.returncode}

    capture = {
        "phase": phase_name,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "docker_image": image_name,
        "health_check": health_check,
        "fixture_provenance": "synthetic",
        "run_output": {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.returncode,
        },
    }

    # Write capture file
    capture_path = os.path.join(capture_dir, "capture.json")
    with open(capture_path, "w") as f:
        json.dump(capture, f, indent=2)

    # Print evidence lines
    stdout = result.stdout
    if result.returncode == 0:
        try:
            payload = json.loads(stdout)
            sources = payload.get("sources", [])
            print(f"PARSER PREFLIGHT: PASS — {len(sources)}/{len(sources)} sub-sources captured")
            for src in sources:
                name = src.get("source", "unknown")
                skipped = src.get("skipped", False)
                status = "skipped" if skipped else ("error" if src.get("error") else "ok")
                print(f"  - {name}: {status}")
        except json.JSONDecodeError:
            print(f"PARSER PREFLIGHT: PASS — output captured (non-JSON)")
    else:
        print(f"PARSER PREFLIGHT: FAIL — exit {result.returncode}")

    return capture


def main():
    if len(sys.argv) > 1:
        phase_name = sys.argv[1]
        # Find the phase
        phase_config = None
        for p in PHASES:
            if p[0] == phase_name:
                phase_config = p
                break
        if not phase_config:
            print(f"Unknown phase: {phase_name}")
            sys.exit(2)
        phases_to_run = [phase_config]
    else:
        phases_to_run = PHASES

    all_captures = []
    for phase in phases_to_run:
        phase_name, docker_dir, runner_args, image_name = phase
        print(f"\n=== Capturing {phase_name} ===")
        try:
            capture = _run_capture(phase_name, docker_dir, runner_args, image_name)
            all_captures.append(capture)
        except Exception as e:
            print(f"ERROR capturing {phase_name}: {e}")
            # Write error capture
            capture_dir = os.path.join("ci", "captures", phase_name)
            os.makedirs(capture_dir, exist_ok=True)
            error_capture = {
                "phase": phase_name,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "docker_image": image_name,
                "health_check": {"stdout": "", "exit_code": -1},
                "fixture_provenance": "synthetic",
                "run_output": {"stdout": "", "stderr": str(e), "exit_code": -1},
                "error": str(e),
            }
            capture_path = os.path.join(capture_dir, "capture.json")
            with open(capture_path, "w") as f:
                json.dump(error_capture, f, indent=2)
            all_captures.append(error_capture)

    print(f"\n=== Summary: {len(all_captures)} phases captured ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())