"""Tests for the egress-proxy component (standalone; not an adapter).

Covers the request-log schema parser, the token-bucket rate limiter and its
persistence, the kill switch, the proxy lifecycle/env helpers, the audit-chain
writer, and the pure helpers inside docker/egress_proxy/proxy.py. No Docker or
network access is required.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from uuid import uuid4

import pytest

from aletheia.core import chain, egress
from aletheia.core.checkpoint import CheckpointStore
from aletheia.core.egress import (
    REQUIRED_LOG_FIELDS,
    AdapterRateLimiter,
    EgressBlocked,
    EgressLogEntry,
    EgressLogError,
    EgressProxy,
    KillSwitch,
    TokenBucket,
    append_log_to_chain,
    parse_log_line,
    read_log,
    should_forward,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "egress_proxy_log.jsonl"


def _load_proxy_module():
    spec = importlib.util.spec_from_file_location(
        "egress_proxy_runner", ROOT / "docker" / "egress_proxy" / "proxy.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fixture_entries() -> list[EgressLogEntry]:
    return read_log(FIXTURE_PATH)


# -- request-log schema --------------------------------------------------------


def test_fixture_log_parses_into_schema_entries():
    entries = _fixture_entries()
    assert len(entries) == 4
    assert [e.request_id for e in entries] == [
        "req-fixture-0001",
        "req-fixture-0002",
        "req-fixture-0003",
        "req-fixture-0004",
    ]
    first = entries[0]
    assert first.adapter == "rdap"
    assert first.method == "GET"
    assert first.host == "rdap.iana.org"
    assert first.path == "/domain/example.com"
    assert first.status == 200
    assert first.bytes == 2048
    assert first.purpose_id == "purpose-fixture-0001"
    # A CONNECT tunnel has an empty path and still validates.
    assert entries[3].method == "CONNECT"
    assert entries[3].path == ""


def test_entry_round_trips_through_dict():
    entry = _fixture_entries()[0]
    assert EgressLogEntry.from_dict(entry.to_dict()) == entry


@pytest.mark.parametrize("field_name", REQUIRED_LOG_FIELDS)
def test_parse_log_line_rejects_missing_field(field_name):
    payload = _fixture_entries()[0].to_dict()
    payload.pop(field_name)
    with pytest.raises(EgressLogError, match="missing field"):
        parse_log_line(json.dumps(payload))


def test_parse_log_line_rejects_non_integer_status():
    payload = _fixture_entries()[0].to_dict()
    payload["status"] = "200"
    with pytest.raises(EgressLogError, match="must be an integer"):
        parse_log_line(json.dumps(payload))


def test_parse_log_line_rejects_boolean_bytes():
    payload = _fixture_entries()[0].to_dict()
    payload["bytes"] = True
    with pytest.raises(EgressLogError, match="must be an integer"):
        parse_log_line(json.dumps(payload))


def test_parse_log_line_rejects_negative_bytes():
    payload = _fixture_entries()[0].to_dict()
    payload["bytes"] = -1
    with pytest.raises(EgressLogError, match=">= 0"):
        parse_log_line(json.dumps(payload))


def test_parse_log_line_rejects_invalid_json():
    with pytest.raises(EgressLogError, match="not valid JSON"):
        parse_log_line("{not json")


def test_parse_log_line_rejects_empty_line():
    with pytest.raises(EgressLogError, match="empty"):
        parse_log_line("   ")


def test_read_log_skips_blank_lines_and_names_bad_lines(tmp_path):
    good = json.dumps(_fixture_entries()[0].to_dict())
    log_path = tmp_path / "EGRESS.jsonl"
    log_path.write_text(good + "\n\n" + good + "\n", encoding="utf-8")
    assert len(read_log(log_path)) == 2

    bad_path = tmp_path / "BAD.jsonl"
    bad_path.write_text(good + "\n" + "{broken\n", encoding="utf-8")
    with pytest.raises(EgressLogError, match=r"BAD\.jsonl:2"):
        read_log(bad_path)


def test_read_log_returns_empty_for_missing_path(tmp_path):
    assert read_log(tmp_path / "does-not-exist.jsonl") == []


# -- rate limiter --------------------------------------------------------------


def test_token_bucket_allows_burst_then_denies():
    bucket = TokenBucket(rate=1.0, capacity=2.0, updated_at=1000.0)
    assert bucket.allow(now=1000.0) is True
    assert bucket.allow(now=1000.0) is True
    assert bucket.allow(now=1000.0) is False


def test_token_bucket_refills_with_injected_clock():
    bucket = TokenBucket(rate=2.0, capacity=2.0, updated_at=0.0)
    assert bucket.allow(now=0.0) is True
    assert bucket.allow(now=0.0) is True
    assert bucket.allow(now=0.0) is False
    # 1 second at rate 2.0 refills the bucket completely.
    assert bucket.allow(now=1.0) is True


def test_token_bucket_rejects_invalid_configuration():
    with pytest.raises(ValueError):
        TokenBucket(rate=0.0, capacity=1.0)
    with pytest.raises(ValueError):
        TokenBucket(rate=1.0, capacity=0.0)
    bucket = TokenBucket(rate=1.0, capacity=1.0)
    with pytest.raises(ValueError):
        bucket.allow(cost=0.0)


def test_rate_limiter_persists_across_restart(tmp_path):
    state_path = tmp_path / "egress-rate.json"
    limiter = AdapterRateLimiter(rate=1.0, capacity=2.0, state_path=state_path)
    assert limiter.allow("rdap", now=1000.0) is True
    assert limiter.allow("rdap", now=1000.0) is True
    assert limiter.allow("rdap", now=1000.0) is False
    # A different adapter has its own bucket.
    assert limiter.allow("search_engines", now=1000.0) is True
    limiter.save()
    assert state_path.exists()

    reloaded = AdapterRateLimiter(rate=1.0, capacity=2.0, state_path=state_path)
    # The drained rdap bucket stays drained immediately after a restart.
    assert reloaded.allow("rdap", now=1000.0) is False
    # ... but refills over wall-clock time.
    assert reloaded.allow("rdap", now=1002.0) is True


# -- kill switch ---------------------------------------------------------------


def test_kill_switch_reads_env_and_flag_file(tmp_path):
    engaged = KillSwitch(environ={egress.KILL_SWITCH_ENV: "yes"})
    assert engaged.engaged() is True
    assert KillSwitch(environ={}).engaged() is False

    flag = tmp_path / "KILL"
    flag.write_text("", encoding="utf-8")
    assert KillSwitch(environ={}, flag_path=flag).engaged() is True

    with pytest.raises(EgressBlocked, match="kill switch"):
        engaged.assert_open()
    KillSwitch(environ={}).assert_open()  # does not raise


def test_should_forward_denies_on_kill_switch_and_rate_limit():
    limiter = AdapterRateLimiter(rate=1.0, capacity=1.0)
    open_switch = KillSwitch(environ={})
    assert should_forward("rdap", kill_switch=open_switch, limiter=limiter, now=0.0) == (True, "ok")
    assert should_forward("rdap", kill_switch=open_switch, limiter=limiter, now=0.0) == (False, "rate_limited")

    engaged = KillSwitch(environ={egress.KILL_SWITCH_ENV: "1"})
    assert should_forward("rdap", kill_switch=engaged, limiter=limiter, now=10.0) == (False, "kill_switch")


# -- proxy lifecycle helpers ---------------------------------------------------


def test_proxy_env_points_adapter_at_the_proxy():
    env = EgressProxy("rdap", port=8888).env_for_adapter()
    assert env["HTTP_PROXY"] == "http://aletheia-egress-rdap:8888"
    assert env["HTTPS_PROXY"] == "http://aletheia-egress-rdap:8888"
    assert env["http_proxy"] == env["HTTP_PROXY"]
    assert env["https_proxy"] == env["HTTPS_PROXY"]


def test_proxy_run_command_sets_adapter_mounts_log_and_kill_switch(tmp_path):
    command = EgressProxy("rdap", kill_switch=True).run_command(log_dir=tmp_path)
    assert command[0] == "docker"
    assert command[-1] == "--serve"
    assert "aletheia/egress-proxy:v1" in command
    assert "ALETHEIA_ADAPTER=rdap" in command
    assert f"{Path(tmp_path).resolve()}:/var/log/aletheia" in command
    assert f"{egress.KILL_SWITCH_ENV}=1" in command
    assert f"{egress.PORT_ENV}=8888" in command


def test_proxy_run_command_resolves_relative_log_dir_for_docker(tmp_path, monkeypatch):
    """Docker rejects a relative bind-mount source as an invalid volume name.

    Run 39119306001 crashed the first live wiring with "includes invalid
    characters for a local volume name" because the operator's ``--data-dir``
    is relative by default. The argv builder must hand Docker an absolute path.
    """
    monkeypatch.chdir(tmp_path)
    command = EgressProxy("rdap").run_command(log_dir=Path("data") / "runs" / "abc" / "rdap" / "egress")
    expected = f"{(tmp_path / 'data' / 'runs' / 'abc' / 'rdap' / 'egress').resolve()}:/var/log/aletheia"
    assert expected in command


# -- audit-chain writer --------------------------------------------------------


def test_append_log_to_chain_records_verified_events(tmp_path):
    run_id = uuid4()
    CheckpointStore(tmp_path / "runs").save(
        run_id, {"goal": "egress chain test", "chain_tip": chain.GENESIS_HASH}
    )
    entries = _fixture_entries()

    count = append_log_to_chain(run_id, entries, data_root=tmp_path)

    assert count == len(entries)
    result = chain.verify(run_id, data_root=tmp_path)
    assert result["valid"] is True
    assert result["first_broken_seq"] is None
    assert result["tip_hash"] == chain.tip(run_id, data_root=tmp_path)
    assert CheckpointStore(tmp_path / "runs").load(run_id)["chain_tip"] == result["tip_hash"]

    audit_path = tmp_path / "runs" / str(run_id) / "AUDIT.jsonl"
    records = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]
    assert [r["event_type"] for r in records] == ["egress_request"] * len(entries)
    assert records[0]["adapter"] == "rdap"
    assert records[0]["request_id"] == "req-fixture-0001"


# -- docker/egress_proxy/proxy.py pure helpers ---------------------------------


def test_proxy_health_prints_ok_without_network(capsys):
    module = _load_proxy_module()
    assert module.main(["--health"]) == 0
    assert capsys.readouterr().out.strip() == "ok"


def test_proxy_parses_request_lines_and_targets():
    module = _load_proxy_module()
    assert module.parse_request_line("GET http://example.com/a HTTP/1.1") == (
        "GET",
        "http://example.com/a",
        "HTTP/1.1",
    )
    with pytest.raises(module.ProxyError):
        module.parse_request_line("garbage")

    assert module.host_port_from_target("GET", "http://example.com:8080/a?b=c") == (
        "example.com",
        8080,
        "/a?b=c",
    )
    assert module.host_port_from_target("GET", "http://example.com/") == ("example.com", 80, "/")
    assert module.host_port_from_target("CONNECT", "example.com:443") == ("example.com", 443, "")
    with pytest.raises(module.ProxyError):
        module.host_port_from_target("GET", "/relative/path")


def test_proxy_log_record_matches_the_reader_schema():
    module = _load_proxy_module()
    record = module.make_log_record(
        adapter="rdap",
        method="GET",
        host="rdap.iana.org",
        path="/domain/example.com",
        status=200,
        nbytes=10,
        purpose_id="p1",
        request_id="req-x",
        timestamp="2026-10-16T20:00:00+00:00",
    )
    # The record the proxy writes is exactly what the control-plane parser reads.
    entry = EgressLogEntry.from_dict(record)
    assert entry.request_id == "req-x"
    assert entry.bytes == 10


def test_proxy_config_reads_environment():
    module = _load_proxy_module()
    config = module.config_from_env({})
    assert config["adapter"] == "unknown"
    assert config["port"] == 8888
    assert config["kill_switch"] is False

    overridden = module.config_from_env({
        "ALETHEIA_ADAPTER": "rdap",
        "ALETHEIA_EGRESS_PORT": "9000",
        "ALETHEIA_EGRESS_KILL_SWITCH": "on",
        "ALETHEIA_EGRESS_LOG": "/tmp/egress.jsonl",
    })
    assert overridden["adapter"] == "rdap"
    assert overridden["port"] == 9000
    assert overridden["kill_switch"] is True
    assert overridden["log_path"] == "/tmp/egress.jsonl"
