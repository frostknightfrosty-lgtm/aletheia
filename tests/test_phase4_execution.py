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
    # The image and command terminate the argv (dedicated test below).
    assert captured["argv"][-4:] == ["aletheia/hibp:api-v3", "runner.py", "email", "x@example.com"]


def test_docker_argv_ends_with_image_and_command(monkeypatch, tmp_path):
    """Run 39120709419: the first live invocation of run_docker sent
    ``docker run <options>`` with no image or command — every adapter died with
    "docker: 'docker run' requires at least 1 argument" while the run still
    reported success. The image and its command must always terminate the argv,
    after the options."""
    captured = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        return type("CP", (), {"stdout": "", "stderr": "", "returncode": 0})()

    monkeypatch.setattr("subprocess.run", fake_run)
    run_docker(
        image="aletheia/maigret:0.6.6",
        command=["exampleuser", "--json", "ndjson", "--folderoutput", "/work/results"],
        workspace=tmp_path,
        timeout_seconds=5,
        proxy_url="http://aletheia-egress-maigret:8888",
        network=True,
        network_name="aletheia-egress-net-maigret",
    )

    argv = captured["argv"]
    assert argv[:2] == ["docker", "run"]
    image_index = argv.index("aletheia/maigret:0.6.6")
    assert argv[image_index + 1:] == ["exampleuser", "--json", "ndjson", "--folderoutput", "/work/results"]
    # Options (network, proxy env, mounts) precede the image.
    assert argv.index("--network") < image_index
