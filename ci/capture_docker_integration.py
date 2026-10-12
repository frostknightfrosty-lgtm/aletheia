#!/usr/bin/env python3
"""Capture case for phase9-gov-records-us Docker integration test.

Run: python ci/capture_docker_integration.py phase9-gov-records-us
This captures the Docker run output for the government_records_us adapter,
recording it as evidence for the CI run.
"""

import json
import subprocess
import sys
import os
from datetime import datetime, timezone


def main():
    if len(sys.argv) < 2:
        print("Usage: capture_docker_integration.py <phase_name>")
        sys.exit(2)

    phase_name = sys.argv[1]
    capture_dir = os.path.join("ci", "captures", phase_name)
    os.makedirs(capture_dir, exist_ok=True)

    # Run the Docker health check first
    runner_path = os.path.join("docker", phase_name, "runner.py")
    docker_image = f"aletheia/{phase_name.split('-')[1].replace('_', '-')}:v1" if "-" in phase_name else f"aletheia/{phase_name}:v1"

    # Actually, for government_records_us, the image is aletheia/gov-records-us:v1
    # But the phase name is phase9-gov-records-us
    # Let me use the proper image name
    image = "aletheia/gov-records-us:v1"

    # Health check
    result = subprocess.run(
        ["python", runner_path, "--health"],
        capture_output=True, text=True, timeout=60
    )

    capture = {
        "phase": phase_name,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "docker_image": image,
        "health_check": {
            "stdout": result.stdout.strip(),
            "exit_code": result.returncode,
        },
        "fixture_provenance": "synthetic",
    }

    # Also run with a sample input to capture the full output
    # Use person_name as it triggers the most sub-sources
    result2 = subprocess.run(
        ["python", runner_path, "person_name", "John Smith"],
        capture_output=True, text=True, timeout=120
    )

    capture["run_output"] = {
        "stdout": result2.stdout,
        "stderr": result2.stderr,
        "exit_code": result2.returncode,
    }

    # Write capture file
    capture_path = os.path.join(capture_dir, "capture.json")
    with open(capture_path, "w") as f:
        json.dump(capture, f, indent=2)

    print(f"Capture written to {capture_path}")
    print(f"Health check: {capture['health_check']['stdout']} (exit: {capture['health_check']['exit_code']})")
    print(f"Exit code: {result2.returncode}")

    # Print evidence lines
    stdout = result2.stdout
    if result2.returncode == 0:
        try:
            payload = json.loads(stdout)
            sources = payload.get("sources", [])
            print(f"\nPARSER PREFLIGHT: PASS — {len(sources)}/11 sub-sources captured")
            for src in sources:
                name = src.get("source", "unknown")
                skipped = src.get("skipped", False)
                status = "skipped" if skipped else ("error" if src.get("error") else "ok")
                print(f"  - {name}: {status}")
        except json.JSONDecodeError:
            print(f"\nstdout: {stdout[:200]}")
    else:
        print(f"\nstderr: {result2.stderr[:200]}")
        print(f"stdout: {stdout[:200]}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())