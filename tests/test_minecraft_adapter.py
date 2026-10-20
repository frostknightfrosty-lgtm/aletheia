"""Fixture/parser and driver tests for the minecraft adapter.

The parser test runs on ``tests/fixtures/minecraft.json`` — a synthetic
normalized document using Mojang's public profile fields. No live Mojang request
is made by this module.
"""

import importlib.util
import json
from pathlib import Path
from uuid import uuid4

import pytest
from parser_test_marker import parser_test

from aletheia.adapters.minecraft import MinecraftAdapter
from aletheia.core.models import AdapterRunRequest, EntityType, Seed, SeedType

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "minecraft.json"
USERNAME = "Notch"
UUID_DASHED = "069a79f4-44e9-4726-a5be-fca90e38aaf5"


def _request(value=USERNAME):
    return AdapterRunRequest(
        run_id=uuid4(), seed=Seed(type=SeedType.USERNAME, value=value)
    )


def _load_driver():
    path = ROOT / "docker" / "minecraft" / "run_minecraft.py"
    spec = importlib.util.spec_from_file_location("minecraft_driver", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _values(result):
    return sorted(finding.value for finding in result.findings)


def test_minecraft_descriptor_scoping():
    adapter = MinecraftAdapter()
    descriptor = adapter.descriptor
    assert descriptor.name == "minecraft"
    assert "Mojang" in descriptor.license
    assert "NameMC" in descriptor.license
    assert descriptor.input_types == [SeedType.USERNAME]
    assert descriptor.output_types == [
        EntityType.SOCIAL_ACCOUNT, EntityType.TECHNICAL_FINDING
    ]
    assert descriptor.network_required is True
    assert descriptor.requires_authorization_assertion is True
    assert descriptor.docker_image == "aletheia/minecraft:v1"
    assert descriptor.upstream == "https://api.mojang.com"
    assert adapter.supports(SeedType.USERNAME) is True
    assert adapter.supports(SeedType.EMAIL) is False


def test_minecraft_build_command_and_username_validation(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    command = MinecraftAdapter().build_command(_request("  Notch  "), workspace)
    assert command == ["/work/username.txt"]
    assert (workspace / "username.txt").read_text(encoding="utf-8") == "Notch\n"
    for bad in ("no", "bad-name", "x" * 17, "space name"):
        with pytest.raises(ValueError):
            MinecraftAdapter().build_command(_request(bad), workspace)


@parser_test("minecraft")
def test_minecraft_fixture_parser_and_markers():
    stdout = FIXTURE.read_text(encoding="utf-8")
    result = MinecraftAdapter().parse(_request(), Path("."), stdout, "", 0)
    assert result.exit_code == 0
    assert result.status == "succeeded"
    assert _values(result) == [
        "minecraft:profile:Notch",
        "minecraft:run:ok",
        f"minecraft:uuid:{UUID_DASHED}",
    ]
    assert len(result.findings) == 3

    by_value = {finding.value: finding for finding in result.findings}
    run = by_value["minecraft:run:ok"]
    assert run.entity_type == EntityType.SOCIAL_ACCOUNT
    assert run.attributes["username"] == USERNAME
    assert run.attributes["uuid_dashed"] == UUID_DASHED
    assert run.attributes["rate_limit_result"] == "UNDER_LIMIT"
    assert run.attributes["errors"] == []
    assert run.provenance.confidence == 0.2

    uuid_finding = by_value[f"minecraft:uuid:{UUID_DASHED}"]
    assert uuid_finding.entity_type == EntityType.TECHNICAL_FINDING
    assert uuid_finding.attributes["kind"] == "minecraft_uuid"
    assert uuid_finding.attributes["uuid"] == "069a79f444e94726a5befca90e38aaf5"
    assert uuid_finding.provenance.confidence == 0.7

    profile = by_value["minecraft:profile:Notch"]
    assert profile.entity_type == EntityType.SOCIAL_ACCOUNT
    assert profile.attributes["platform"] == "minecraft"
    assert profile.attributes["skin_model"] == "slim"
    assert profile.attributes["skin_url"].startswith("https://textures.minecraft.net/")
    assert profile.attributes["name_history"] == "not collected"
    assert profile.provenance.confidence == 0.6


def test_minecraft_parser_not_found_partial_and_malformed():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload.update({"status": "not_found", "uuid": None, "uuid_dashed": None})
    result = MinecraftAdapter().parse(_request(), Path("."), json.dumps(payload), "", 0)
    assert result.status == "succeeded"
    assert _values(result) == ["minecraft:run:not_found"]

    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["status"] = "partial"
    payload["errors"] = ["session: HTTP 429"]
    result = MinecraftAdapter().parse(_request(), Path("."), json.dumps(payload), "", 0)
    assert result.status == "partial"
    assert len(result.findings) == 3
    assert result.findings[0].attributes["errors"] == ["session: HTTP 429"]

    result = MinecraftAdapter().parse(_request(), Path("."), "not json", "", 1)
    assert result.status == "partial"
    assert _values(result) == ["minecraft:run:error"]


def test_minecraft_driver_textures_and_normalisation():
    driver = _load_driver()
    textures = driver._decode_textures([
        {"name": "textures", "value": driver._SAMPLE_TEXTURE}
    ])
    assert textures["skin_model"] == "slim"
    assert textures["skin_url"].startswith("https://textures.minecraft.net/texture/")
    assert textures["cape_url"] is None
    assert driver._decode_textures([{"name": "textures", "value": "!!!"}]) == {}
    assert driver._decode_textures("not a list") == {}

    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    normalized = driver._normalise(raw)
    assert normalized["status"] == "ok"
    assert normalized["uuid"] == "069a79f444e94726a5befca90e38aaf5"
    assert normalized["uuid_dashed"] == UUID_DASHED
    assert normalized["skin_model"] == "slim"
    assert normalized["skin_url"].startswith("https://textures.minecraft.net/")

    assert driver._safe_texture_url("https://evil.example/texture/x") is None
    assert driver._safe_texture_url("https://textures.minecraft.net/not-a-texture") is None
    assert driver._dashed("069a79f444e94726a5befca90e38aaf5") == UUID_DASHED


def test_minecraft_driver_invalid_documents_and_args():
    driver = _load_driver()
    for bad in ({}, {"source": "other", "username": USERNAME},
                {"source": "minecraft", "status": "ok", "username": "no"}):
        with pytest.raises(ValueError):
            driver._normalise(bad)

    assert driver._parse_args(["--health"]).health is True
    assert driver._parse_args(["--selftest"]).selftest is True
    parsed = driver._parse_args(["--normalize", "profile.json"])
    assert parsed.normalize == "profile.json"
    assert parsed.username_file is None
    assert driver._parse_args(["username.txt"]).username_file == "username.txt"
