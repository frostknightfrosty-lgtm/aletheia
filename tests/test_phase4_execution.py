import os
from pathlib import Path

from aletheia.core.execution import run_docker, ExecutionResult


def test_secret_values_never_enter_docker_argv(monkeypatch, tmp_path):
    captured = {}
    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        return type("CP", (), {"stdout": "", "stderr": "", "returncode": 0})()
    monkeypatch.setattr("subprocess.run", fake_run)
    monkeypatch.setenv("HIBP_API_KEY", "SUPER-SECRET")
    result = run_docker(image="aletheia/hibp:api-v3", command=["runner.py", "email", "x@example.com"],
                        workspace=tmp_path, timeout_seconds=5, proxy_url=None, network=True,
                        secret_env=["HIBP_API_KEY"])
    assert result == ExecutionResult("", "", 0)
    argv = " ".join(captured["argv"])
    assert "SUPER-SECRET" not in argv
    assert "-e HIBP_API_KEY" in argv
