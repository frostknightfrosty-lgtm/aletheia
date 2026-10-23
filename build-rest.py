import subprocess, json, time, sys, os
with open('docker/build.sh') as f:
    cmds = [l for l in f.read().splitlines() if l.startswith('docker build')]
start_idx = 24  # start after first 24 OK images
results = []
with open('docker-build-sequential.log', 'w') as log:
    for i in range(start_idx, len(cmds)):
        cmd = cmds[i]
        label = f"[{i+1}/{len(cmds)}] {cmd[:70]}"
        log.write(f"START {label}\n")
        print(f"BUILD {label}")
        health = subprocess.run('docker info --format "{{.Server.Version}}"', shell=True, capture_output=True, text=True)
        if health.returncode != 0 or '29.8.2' not in (health.stdout or ''):
            log.write("DAEMON DOWN - SKIPPING REMAINING\n")
            print("  DAEMON DOWN - skipping rest")
            break
        proc = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        log.write(f"END exit={proc.returncode}\n")
        if proc.stdout:
            log.write(proc.stdout[-400:] if len(proc.stdout) > 400 else proc.stdout)
        if proc.stderr:
            log.write(proc.stderr[-400:] if len(proc.stderr) > 400 else proc.stderr)
        results.append({'cmd': cmd[:70], 'exit': proc.returncode, 'dur': 0})
        status = 'OK' if proc.returncode == 0 else 'FAIL'
        print(f"  -> {status} exit={proc.returncode}")
        if proc.returncode != 0:
            stderr_text = proc.stderr or ''
            if 'deepface' in cmd or 'insightface' in cmd or 'core.Dockerfile' in cmd:
                log.write("SKIP: known crash-prone image; continuing.\n")
            elif 'npipe' in stderr_text or 'dockerDesktopLinuxEngine' in stderr_text or 'read-only file system' in stderr_text:
                log.write("DAEMON CRASH DETECTED - stopping sequence to prevent further crashes.\n")
                print("  DAEMON CRASH - stopping sequence")
                break
        time.sleep(1)
with open('build-sequential-rest.json', 'w') as f:
    json.dump({'total_attempted': len(results), 'ok': sum(1 for r in results if r['exit']==0), 'fail': sum(1 for r in results if r['exit']!=0), 'results': results}, f, indent=2)
print("Sequential rest complete.")
print("Attempted:", len(results), "OK:", sum(1 for r in results if r['exit']==0), "FAIL:", sum(1 for r in results if r['exit']!=0))
