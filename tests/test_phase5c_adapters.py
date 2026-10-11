from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from uuid import uuid4

import pytest
from parser_test_marker import parser_test

from aletheia.adapters.phase5c import GravatarAdapter
from aletheia.adapters.registry import phase7_adapters
from aletheia.core.audit import AuditLogger
from aletheia.core.execution import DockerExecutionError
from aletheia.core.models import AdapterRunRequest, EntityType, Seed, SeedType

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "gravatar.json"
EMAIL = "test@example.com"
EMAIL_HASH = hashlib.sha256(EMAIL.encode()).hexdigest()
EXCLUDED_FIELDS = {
    "contact_info", "payments", "links", "gallery", "verified_accounts",
    "section_visibility", "avatar_alt_text", "pronouns",
}


def _request(value: str = EMAIL, assertion: str | None = "authorized email investigation") -> AdapterRunRequest:
    return AdapterRunRequest(
        run_id=uuid4(), seed=Seed(type=SeedType.EMAIL, value=value),
        legal_only=True, authorization_assertion=assertion,
    )


def _load_runner():
    spec = importlib.util.spec_from_file_location("gravatar_runner", ROOT / "docker" / "gravatar" / "runner.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_gravatar_is_registered_and_rdap_is_not():
    registry = phase7_adapters()
    assert "gravatar" in registry
    assert "rdap" not in registry
    descriptor = registry["gravatar"].descriptor
    assert descriptor.input_types == [SeedType.EMAIL]
    assert descriptor.requires_authorization_assertion is True
    assert descriptor.network_required is True
    assert descriptor.docker_image == "aletheia/gravatar:api-v3"


def test_gravatar_requires_authorization_before_docker(monkeypatch, tmp_path):
    import aletheia.core.adapters as core_adapters
    called = False

    def fake_run_docker(**kwargs):
        nonlocal called
        called = True
        raise DockerExecutionError("must not execute")

    monkeypatch.setattr(core_adapters, "run_docker", fake_run_docker)
    with pytest.raises(ValueError, match="authorization_assertion"):
        GravatarAdapter().run(_request(assertion=None), tmp_path / "gravatar", AuditLogger(tmp_path / "audit.jsonl"))
    assert called is False


def test_gravatar_command_passes_only_hash_arguments_and_never_the_email():
    # The image ENTRYPOINT already supplies `python /opt/runner.py`; the command is arguments only.
    command = GravatarAdapter().build_command(_request(" Test@Example.com "), Path("."))
    assert command == ["hash", EMAIL_HASH]
    assert not any("@" in part for part in command)


@parser_test("gravatar")
def test_gravatar_parser_keeps_only_curated_fields():
    stdout = FIXTURE.read_text(encoding="utf-8")
    result = GravatarAdapter().parse(_request(), Path("."), stdout, "", 0)
    assert len(result.findings) == 1
    finding = result.findings[0]
    assert finding.entity_type == EntityType.SOCIAL_ACCOUNT
    assert finding.value == "https://gravatar.com/aletheia-synthetic-test"
    assert finding.attributes["email_sha256"] == EMAIL_HASH
    assert finding.attributes["display_name"] == "Synthetic Test Profile"
    assert not (EXCLUDED_FIELDS & set(finding.attributes))
    assert "is_organization" not in finding.attributes  # False is not emitted
    flattened = json.dumps(finding.attributes)
    assert "+1555" not in flattened and "0x0000" not in flattened and EMAIL not in flattened
    assert finding.provenance.source_url == f"https://api.gravatar.com/v3/profiles/{EMAIL_HASH}"
    assert finding.provenance.raw_evidence_sha256 == hashlib.sha256(stdout.encode()).hexdigest()
    assert "not identity confirmation" in finding.provenance.notes[0]


def test_gravatar_parser_rejects_hash_mismatch_not_found_and_garbage():
    stdout = FIXTURE.read_text(encoding="utf-8")
    adapter = GravatarAdapter()
    assert not adapter.parse(_request("different@example.com"), Path("."), stdout, "", 0).findings
    assert not adapter.parse(_request(), Path("."), json.dumps({"http_status": 404, "status": "not_found"}), "", 0).findings
    assert not adapter.parse(_request(), Path("."), "not json", "", 0).findings
    assert not adapter.parse(_request(), Path("."), "", "", 4).findings


def test_gravatar_parser_drops_non_https_urls():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["avatar_url"] = "http://0.gravatar.com/avatar/x"
    kept = GravatarAdapter().parse(_request(), Path("."), json.dumps(payload), "", 0)
    assert "avatar_url" not in kept.findings[0].attributes
    payload["profile_url"] = "javascript:alert(1)"
    assert not GravatarAdapter().parse(_request(), Path("."), json.dumps(payload), "", 0).findings


def test_gravatar_runner_curates_before_output():
    runner = _load_runner()
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    curated = runner.curate(payload, EMAIL_HASH)
    assert curated is not None
    assert set(curated) <= {"hash", "profile_url", "avatar_url", "display_name", "location",
                            "description", "job_title", "company", "is_organization"}
    assert not (EXCLUDED_FIELDS & set(curated))
    assert runner.curate(payload, "0" * 64) is None
    assert runner.curate(["not", "a", "dict"], EMAIL_HASH) is None


def test_gravatar_runner_argument_validation(monkeypatch, capsys):
    runner = _load_runner()
    for argv in (["runner.py"], ["runner.py", "hash"], ["runner.py", "hash", EMAIL],
                 ["runner.py", "email", EMAIL_HASH], ["runner.py", "hash", EMAIL_HASH.upper()]):
        monkeypatch.setattr("sys.argv", argv)
        assert runner.main() == 2
    monkeypatch.setattr("sys.argv", ["runner.py", "--health"])
    assert runner.main() == 0
    assert capsys.readouterr().out.strip().endswith("ok")
