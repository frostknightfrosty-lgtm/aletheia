"""Fixture/parser tests for the SpiderFoot 4.0 meta-adapter.

The fixture is synthetic and follows SpiderFoot's documented JSON event shape:
each event has ``generated``, ``type``, ``data``, ``module`` and ``source``.
No live SpiderFoot scan is performed here.
"""
from __future__ import annotations

import importlib.util
import json
import sqlite3
from pathlib import Path
from uuid import uuid4

import pytest
from parser_test_marker import parser_test

from aletheia.adapters.spiderfoot import MODULE_CATALOG, SpiderFootAdapter
from aletheia.cascade.claims import claim_from_finding
from aletheia.cascade.extractors import extract_pivots
from aletheia.cascade.routing import build_routing_graph
from aletheia.core.graph import Graph
from aletheia.phase2.resolution import EntityResolver
from aletheia.core.models import (
    AdapterRunRequest,
    EntityType,
    Finding,
    Provenance,
    Seed,
    SeedType,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "spiderfoot.json"


def _request(value: str = "example.com") -> AdapterRunRequest:
    return AdapterRunRequest(run_id=uuid4(), seed=Seed(type=SeedType.DOMAIN, value=value))


def _load_runner():
    path = ROOT / "docker" / "spiderfoot" / "runner.py"
    spec = importlib.util.spec_from_file_location("spiderfoot_runner", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _by_type(result) -> dict[EntityType, list[Finding]]:
    grouped: dict[EntityType, list[Finding]] = {}
    for finding in result.findings:
        grouped.setdefault(finding.entity_type, []).append(finding)
    return grouped


def test_spiderfoot_descriptor_scoping_and_catalog():
    adapter = SpiderFootAdapter()
    descriptor = adapter.descriptor
    assert descriptor.name == "spiderfoot"
    assert descriptor.docker_image == "aletheia/spiderfoot:v4.0"
    assert descriptor.network_required is True
    assert descriptor.requires_authorization_assertion is True
    assert descriptor.version_pin.startswith("4.0.0 (b9c345de")
    assert descriptor.input_types == [
        SeedType.DOMAIN, SeedType.IP, SeedType.EMAIL, SeedType.USERNAME, SeedType.PHONE
    ]
    assert EntityType.BREACH_HIT in descriptor.output_types
    assert "HIBP_API_KEY" in descriptor.secret_env
    assert "INTELX_API_KEY" in descriptor.secret_env
    assert "C99_API_KEY" in descriptor.secret_env
    for seed_type in descriptor.input_types:
        assert adapter.supports(seed_type) is True
    assert adapter.supports(SeedType.URL) is False
    assert adapter.supports(SeedType.NAME) is False

    assert len(MODULE_CATALOG) == 14
    assert MODULE_CATALOG["sfp_intelx"]["legal_tier"] == 4
    assert MODULE_CATALOG["sfp_haveibeenpwned"]["env"] == "HIBP_API_KEY"
    assert MODULE_CATALOG["sfp_abusech"]["requires_key"] is False


@parser_test("spiderfoot")
def test_spiderfoot_fixture_mappings_provenance_and_priority():
    stdout = FIXTURE.read_text(encoding="utf-8")
    result = SpiderFootAdapter().parse(_request(), Path("."), stdout, "", 0)
    assert result.status == "succeeded"
    assert result.exit_code == 0
    assert len(result.findings) == 19
    assert all(finding.source_priority == "secondary" for finding in result.findings)
    assert all(finding.attributes["source_priority"] == "secondary" for finding in result.findings)

    grouped = _by_type(result)
    assert any(f.value == "example.com" for f in grouped[EntityType.DOMAIN])
    assert any(f.value == "203.0.113.10" for f in grouped[EntityType.IP])
    assert any(f.value == "alice@example.com" for f in grouped[EntityType.EMAIL])
    assert any(f.value == "alice_example" for f in grouped[EntityType.USERNAME])
    assert any(f.value == "https://twitter.com/alice_example" for f in grouped[EntityType.URL])
    assert any(f.value == "alice@example.com:example-password" for f in grouped[EntityType.BREACH_HIT])
    assert any(f.value == "Example Corp" for f in grouped[EntityType.COMPANY])
    assert any(f.value == "Alice Example" for f in grouped[EntityType.PERSON])

    domain = next(f for f in grouped[EntityType.DOMAIN] if f.value == "example.com")
    assert domain.provenance.tool == "spiderfoot"
    assert domain.provenance.source_url == "https://www.threatcrowd.org/"
    assert any("sfp_threatcrowd" in note for note in domain.provenance.notes)
    assert any("legal tier 1" in note for note in domain.provenance.notes)
    assert len(domain.provenance.raw_evidence_sha256 or "") == 64

    breach = next(f for f in grouped[EntityType.BREACH_HIT] if f.value.startswith("alice@"))
    assert breach.attributes["data_source"] == "Have I Been Pwned"
    assert breach.attributes["legal_tier"] == 4
    assert breach.attributes["spiderfoot_event_type"] == "LEAKSITE_CONTENT"
    assert any(
        finding.value == "alice@example.com"
        and finding.attributes.get("from_leak_content") is True
        for finding in grouped[EntityType.EMAIL]
    )

    # The IP appears from both Robtex and ThreatFox. The graph keeps one node
    # and the native/secondary precedence rules remain available to the merge.
    graph = Graph()
    for finding in grouped[EntityType.IP]:
        graph.ingest(finding)
    ip_entities = [e for e in graph.entities.values() if e.entity_type == EntityType.IP]
    assert len(ip_entities) == 1
    assert ip_entities[0].attributes["source_priority"] == "secondary"


def test_spiderfoot_secondary_email_feeds_cascade_pivot():
    finding = Finding(
        entity_type=EntityType.EMAIL,
        value="New.Person@example.com",
        attributes={"source": "spiderfoot", "source_priority": "secondary"},
        provenance=Provenance(
            tool="spiderfoot",
            confidence=0.6,
            adapter_version="4.0.0",
            source_url="https://hunter.io/",
        ),
        source_priority="secondary",
    )
    claim = claim_from_finding(finding)
    assert claim.value == "new.person@example.com"
    assert claim.attributes["source_priority"] == "secondary"
    pivots = extract_pivots(claim)
    assert any(p.seed.type is SeedType.EMAIL and p.seed.value == "new.person@example.com" for p in pivots)

    # The live routing graph is descriptor-derived: the new email can still
    # reach the native Holehe and H8mail adapters, while SpiderFoot is also a
    # legitimate route. Secondary priority does not suppress native pivots.
    routes = build_routing_graph().adapters_for_seed(SeedType.EMAIL)
    assert {"holehe", "h8mail", "spiderfoot"} <= set(routes)


def test_spiderfoot_graph_primary_wins_attribute_conflict():
    primary = Finding(
        entity_type=EntityType.IP,
        value="203.0.113.10",
        attributes={"classification": "benign", "source": "native-shodan"},
        provenance=Provenance(tool="shodan", confidence=0.9, adapter_version="1.0"),
        source_priority="primary",
    )
    secondary = Finding(
        entity_type=EntityType.IP,
        value="203.0.113.10",
        attributes={"classification": "malicious", "source": "spiderfoot", "extra": "secondary-only"},
        provenance=Provenance(tool="spiderfoot", confidence=0.6, adapter_version="4.0.0"),
        source_priority="secondary",
    )
    graph = Graph()
    entity, _ = graph.ingest(primary)
    secondary_entity, _ = graph.ingest(secondary)
    assert entity.entity_id == secondary_entity.entity_id
    assert entity.attributes["classification"] == "benign"
    assert entity.attributes["source_priority"] == "primary"
    assert entity.attributes["extra"] == "secondary-only"


def test_spiderfoot_secondary_only_fuzzy_pairs_do_not_create_candidates():
    secondary_graph = Graph()
    secondary_graph.upsert_entity(
        EntityType.USERNAME, "alice123", {"source_priority": "secondary"}
    )
    secondary_graph.upsert_entity(
        EntityType.USERNAME, "alice124", {"source_priority": "secondary"}
    )
    resolver = EntityResolver(fetch_avatars=False)
    assert resolver.resolve(secondary_graph) == []

    mixed_graph = Graph()
    mixed_graph.upsert_entity(
        EntityType.USERNAME, "alice123", {"source_priority": "primary"}
    )
    mixed_graph.upsert_entity(
        EntityType.USERNAME, "alice124", {"source_priority": "secondary"}
    )
    resolver = EntityResolver(fetch_avatars=False)
    candidates = resolver.resolve(mixed_graph)
    assert len(candidates) == 1
    assert candidates[0].decision == "candidate"


def test_spiderfoot_envelope_skip_records_and_errors():
    payload = {
        "source": "spiderfoot",
        "version": "4.0.0",
        "status": "ok",
        "seed": {"type": "email", "value": "alice@example.com"},
        "modules_run": ["sfp_threatcrowd"],
        "skipped": [{
            "module": "sfp_hunter",
            "source": "Hunter",
            "requires_key": True,
            "env": "HUNTER_API_KEY",
            "legal_tier": 3,
            "reason": "HUNTER_API_KEY is not set",
        }],
        "events": [{
            "generated": "2026-10-23 12:00:06",
            "type": "EMAILADDR",
            "data": "alice@example.com",
            "module": "sfp_threatcrowd",
            "source": "ROOT",
        }],
        "errors": [],
        "stderr_tail": "",
    }
    result = SpiderFootAdapter().parse(_request(), Path("."), json.dumps(payload), "", 0)
    assert result.status == "succeeded"
    assert len(result.findings) == 2
    skip = next(f for f in result.findings if f.attributes.get("details", {}).get("skipped"))
    assert skip.entity_type == EntityType.TECHNICAL_FINDING
    assert skip.attributes["details"]["reason"] == "HUNTER_API_KEY is not set"
    assert skip.attributes["legal_tier"] == 3
    assert skip.source_priority == "secondary"

    payload["status"] = "partial"
    payload["errors"] = ["sfp_hunter skipped: HUNTER_API_KEY is not set"]
    result = SpiderFootAdapter().parse(_request(), Path("."), json.dumps(payload), "", 0)
    assert result.status == "partial"
    assert any(f.value == "spiderfoot:run:errors" for f in result.findings)

    payload["status"] = "failed"
    payload["errors"] = ["SpiderFoot exited with code 2"]
    result = SpiderFootAdapter().parse(_request(), Path("."), json.dumps(payload), "", 2)
    assert result.status == "failed"
    assert result.exit_code == 2


def test_spiderfoot_malformed_output_is_partial_with_error_finding():
    result = SpiderFootAdapter().parse(_request(), Path("."), "not json", "boom", 1)
    assert result.status == "partial"
    assert result.exit_code == 1
    assert len(result.findings) == 1
    assert result.findings[0].entity_type == EntityType.TECHNICAL_FINDING
    assert result.findings[0].value == "spiderfoot:run:errors"
    assert "not valid JSON" in result.findings[0].attributes["details"]["errors"][0]
    assert result.stderr_tail == "boom"


def test_spiderfoot_build_command_uses_seed_type_value():
    adapter = SpiderFootAdapter()
    assert adapter.build_command(_request("  Example.COM  "), Path(".")) == ["domain:Example.COM"]
    with pytest.raises(ValueError):
        adapter.build_command(_request("   "), Path("."))


def test_spiderfoot_runner_seed_parsing_and_module_selection():
    runner = _load_runner()
    assert len(runner.MODULES) == 14
    assert runner.parse_seed("domain:Example.COM.") == {
        "type": "domain", "value": "example.com", "spiderfoot_type": "INTERNET_NAME"
    }
    assert runner.parse_seed("ip:2001:db8::1")["value"] == "2001:db8::1"
    assert runner.parse_seed("email:Test@Example.COM")["value"] == "Test@example.com"
    assert runner.parse_seed("username:@frost2233")["value"] == "frost2233"
    assert runner.parse_seed("phone:+1 (555) 123-4567")["value"] == "+15551234567"
    for bad in ("example.com", "domain:", "url:https://example.com", "ip:nope", "domain:not-a-domain"):
        with pytest.raises(runner.SeedError):
            runner.parse_seed(bad)

    runnable, skipped = runner.select_modules({})
    assert len(runnable) == 8
    assert len(skipped) == 6
    assert {item["env"] for item in skipped} == {
        "EMAILREP_API_KEY", "HUNTER_API_KEY", "PULSEDIVE_API_KEY",
        "INTELX_API_KEY", "C99_API_KEY", "HIBP_API_KEY",
    }
    all_env = {item["env"]: "test-key" for item in runner.MODULES if item["env"]}
    runnable, skipped = runner.select_modules(all_env)
    assert len(runnable) == 14
    assert skipped == []

    seed = runner.parse_seed("username:john.doe")
    command = runner.build_scan_command(seed, ["sfp_keybase"])
    assert command[0:2] == ["python3", "sf.py"]
    assert command[2:6] == ["-s", '"john.doe"', "-t", "USERNAME"]
    assert command[6:] == ["-o", "json", "-q", "-m", "sfp_keybase"]


def test_spiderfoot_runner_key_configuration_is_scrubbed(tmp_path):
    runner = _load_runner()
    db_path, injected = runner._inject_api_keys(
        tmp_path, ["sfp_hunter"], {"HUNTER_API_KEY": "unit-test-key"}
    )
    assert injected == 1
    connection = sqlite3.connect(db_path)
    try:
        row = connection.execute(
            "SELECT val FROM tbl_config WHERE scope='sfp_hunter' AND opt='api_key'"
        ).fetchone()
        assert row[0] == "unit-test-key"
    finally:
        connection.close()
    runner._scrub_api_keys(db_path)
    connection = sqlite3.connect(db_path)
    try:
        assert connection.execute(
            "SELECT COUNT(*) FROM tbl_config WHERE opt='api_key'"
        ).fetchone()[0] == 0
    finally:
        connection.close()
