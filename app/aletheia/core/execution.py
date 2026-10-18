from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


class DockerExecutionError(RuntimeError):
    pass


@dataclass(frozen=True)
class ExecutionResult:
    stdout: str
    stderr: str
    exit_code: int


def run_docker(*, image: str, command: Sequence[str], workspace: Path, timeout_seconds: int,
               proxy_url: str | None, network: bool, secret_env: Sequence[str] = (),
               network_name: str | None = None) -> ExecutionResult:
    argv = [
        "docker", "run", "--rm",
        "--read-only",
        "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m",
        "-v", f"{workspace.resolve()}:/work:rw",
        "--workdir", "/work",
    ]
    if network_name is not None:
        # Join a caller-provided network (the egress proxy's internal network).
        argv += ["--network", network_name]
    elif network:
        argv += ["--network", "bridge"]
    else:
        argv += ["--network", "none"]
    if proxy_url:
        argv += ["-e", f"HTTP_PROXY={proxy_url}", "-e", f"HTTPS_PROXY={proxy_url}", "-e", f"ALL_PROXY={proxy_url}"]
    env = os.environ.copy()
    for key in secret_env:
        if env.get(key):
            # Pass only the variable name; Docker reads its value from the child environment.
            # This keeps secrets out of argv and Aletheia audit records.
            argv += ["-e", key]
    # Avoid leaking host credentials/config into child containers.
    for key in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "GITHUB_TOKEN", "OPENAI_API_KEY"):
        env.pop(key, None)
    # The image and its command terminate the argv: `docker run [options]
    # <image> <command...>`. Run 39120709419 was the first live invocation this
    # function ever executed and every adapter died with "docker: 'docker run'
    # requires at least 1 argument" because this append was missing — yet the
    # run still reported success (see phase2's result-status reporting).
    argv += [image, *command]
    try:
        completed = subprocess.run(argv, capture_output=True, text=True, timeout=timeout_seconds, env=env)
    except FileNotFoundError as exc:
        raise DockerExecutionError("Docker CLI is not installed") from exc
    except subprocess.TimeoutExpired as exc:
        raise DockerExecutionError(f"container timed out after {timeout_seconds}s") from exc
    return ExecutionResult(completed.stdout, completed.stderr, completed.returncode)
