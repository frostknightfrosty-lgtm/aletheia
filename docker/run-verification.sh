#!/usr/bin/env bash
set -euo pipefail
cd /workspace
mkdir -p ci-artifacts
PYTHONPATH=app python ci/check_parser_coverage.py | tee ci-artifacts/parser-preflight.txt
./docker/build.sh 2>&1 | tee ci-artifacts/docker-build.log
python - <<'PY' | tee ci-artifacts/image-ids-and-dockerfile-sha256.txt
import re, subprocess
from pathlib import Path
images=[]
for line in Path('docker/build.sh').read_text().splitlines():
    if line.strip().startswith('docker build '):
        m=re.search(r'-t\s+(\S+)', line)
        if m: images.append(m.group(1))
for image in sorted(set(images)):
    out=subprocess.run(['docker','image','inspect',image,'--format','{{.Id}} {{.Created}}'],text=True,capture_output=True,check=True)
    print(f'{image} {out.stdout.strip()}')
print('--- Dockerfile SHA256 ---')
for f in sorted(Path('docker').rglob('Dockerfile')):
    out=subprocess.run(['sha256sum',str(f)],text=True,capture_output=True,check=True)
    print(out.stdout.strip())
PY
python -m pytest -q 2>&1 | tee ci-artifacts/pytest-full.log
python ci/capture_docker_integration.py 2>&1 | tee ci-artifacts/docker-integration/capture.log
touch ci-artifacts/CI_SUCCESS
echo 'CI READY HARNESS: PASS'
