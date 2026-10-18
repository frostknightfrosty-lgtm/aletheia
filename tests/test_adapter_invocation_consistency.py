"""Every adapter's docker command must be arguments to its image ENTRYPOINT.

Run 39120709419 was the first run in which ``run_docker`` ever executed a real
container (the argv was missing the image entirely until the same repair). It
exposed a second latent class: 29 of 49 adapters restated their image's
entrypoint inside ``build_command`` — ``docker run <image> maigret ...`` where
the image entrypoint is already ``maigret``, or a leading ``runner.py`` where
the entrypoint is ``python /opt/runner.py``. Both mistakes are instant usage
errors on the first real invocation, and neither shows up in parsing tests
because parsing tests feed captured output directly to ``parse``.

This test pins the contract mechanically: for every registered adapter, build
the command with a sample seed and check it against the ``ENTRYPOINT`` parsed
from the Dockerfile that ``docker/build.sh`` builds the adapter's image from.
"""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

import pytest

from aletheia.adapters.registry import phase7_adapters
from aletheia.core.models import AdapterRunRequest, Seed, SeedType

ROOT = Path(__file__).resolve().parents[1]


def _image_dockerfiles() -> dict[str, Path]:
    """docker/build.sh is the authoritative image -> Dockerfile mapping."""
    mapping: dict[str, Path] = {}
    for line in (ROOT / "docker" / "build.sh").read_text(encoding="utf-8").splitlines():
        match = re.match(r"docker build (?:-f (\S+) )?-t (\S+) (\S+)$", line.strip())
        if not match:
            continue
        dockerfile, image, context = match.groups()
        mapping[image] = ROOT / (dockerfile or f"{context}/Dockerfile")
    return mapping


def _entrypoint(dockerfile: Path) -> list[str] | None:
    for line in dockerfile.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.upper().startswith("ENTRYPOINT"):
            return json.loads(stripped.split("ENTRYPOINT", 1)[1].strip())
    return None


def _sample_request(seed_type: SeedType, tmp_path: Path) -> AdapterRunRequest:
    file_input = tmp_path / "sample.bin"
    file_input.write_bytes(b"aletheia")
    image_input = tmp_path / "sample.jpg"
    image_input.write_bytes(b"\xff\xd8\xff\xe0")
    values = {
        SeedType.USERNAME: "exampleuser",
        SeedType.NAME: "Acme Corporation",
        SeedType.EMAIL: "a@example.com",
        SeedType.PHONE: "+14155552671",
        SeedType.DOMAIN: "example.com",
        SeedType.URL: "https://example.com/profile",
        SeedType.IP: "203.0.113.10",
        SeedType.FILE_PATH: str(file_input),
        SeedType.IMAGE: str(image_input),
        SeedType.GEOLOCATION: "37.7749,-122.4194",
        SeedType.COMPANY_NAME: "Acme Corporation",
        SeedType.BANK_NAME: "Example Bank",
        SeedType.VIN: "1HGCM82633A004352",
        SeedType.PERSON_NAME: "Jane Doe",
        SeedType.LOBBYIST_NAME: "Jane Doe",
        SeedType.CRYPTO_ADDRESS: "12dRugNcdxK39288NjcDV4GX7rMsKCGn6B",
        SeedType.INTELLECTUAL_PROPERTY: "US1234567",
    }
    return AdapterRunRequest(
        run_id=uuid.uuid4(),
        seed=Seed(type=seed_type, value=values[seed_type]),
        legal_only=True,
        authorization_assertion="adapter invocation consistency test",
    )


_ADAPTERS = phase7_adapters()


@pytest.mark.parametrize("name", sorted(_ADAPTERS))
def test_build_command_is_arguments_to_the_image_entrypoint(name, tmp_path):
    adapter = _ADAPTERS[name]
    docker_image = adapter.descriptor.docker_image
    image_dockerfiles = _image_dockerfiles()
    assert docker_image in image_dockerfiles, f"{docker_image} is not built by docker/build.sh"

    entrypoint = _entrypoint(image_dockerfiles[docker_image])
    assert entrypoint, f"no ENTRYPOINT in the Dockerfile for {docker_image}"

    seed_type = adapter.descriptor.input_types[0]
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    command = adapter.build_command(_sample_request(seed_type, tmp_path), workspace)

    assert command and all(isinstance(part, str) for part in command)
    assert str(workspace) not in " ".join(command), (
        "the command runs inside the container; a host workspace path can never exist there"
    )
    # The command must not restate the entrypoint: the image already supplies it.
    assert command[: len(entrypoint)] != entrypoint, "command repeats the image ENTRYPOINT"
    assert Path(entrypoint[0]).name != Path(command[0]).name, "command repeats the entrypoint program"
    if len(entrypoint) >= 2:
        assert Path(entrypoint[-1]).name not in command[0], "command repeats the entrypoint script"
