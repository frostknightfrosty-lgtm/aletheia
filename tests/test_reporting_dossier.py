"""Phase 18.3 local-LLM dossier tests.

The LLM is an injected fake, so these tests never need Ollama or network access.
The audit fixture is a real hash chain written by ``AuditLogger``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from aletheia.cli.main import build_parser, main, parse_ask_query
from aletheia.core.audit import AuditLogger
from aletheia.core.models import AuditEvent, Seed, SeedType
from aletheia.reporting.dossier import generate_dossier


class _FakeCompletions:
    def __init__(self, content: str) -> None:
        self.content = content
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self.content))]
        )


class _FakeClient:
    def __init__(self, content: str = "# Dossier\n\nEvidence: github-identity.") -> None:
        self.completions = _FakeCompletions(content)
        self.chat = SimpleNamespace(completions=self.completions)


def _run_artifacts(tmp_path: Path) -> tuple[Path, str, UUID]:
    data = tmp_path / "data"
    run_id = uuid4()
    run_dir = data / "runs" / str(run_id)
    graph_dir = data / "graphs" / str(run_id)
    run_dir.mkdir(parents=True)
    graph_dir.mkdir(parents=True)

    graph = {
        "entities": [
            {
                "entity_id": str(uuid4()),
                "entity_type": "social_account",
                "canonical_value": "https://github.com/jdoe88",
                "attributes": {
                    "platform": "github",
                    "username": "jdoe88",
                    "tool": "github-identity",
                    "source_url": "https://api.github.com/users/jdoe88",
                },
            }
        ],
        "edges": [],
    }
    (graph_dir / "graph.json").write_text(json.dumps(graph), encoding="utf-8")
    resolution = {
        "run_id": str(run_id),
        "candidate_count": 0,
        "candidates": [],
        "confirmed_link_count": 1,
        "confirmed_links": [
            {
                "source": "text_embedding",
                "confidence": 0.85,
                "left_value": "https://github.com/jdoe88",
                "right_value": "https://reddit.com/user/john.doe",
            }
        ],
    }
    (run_dir / "resolution.json").write_text(
        json.dumps(resolution), encoding="utf-8"
    )
    audit = AuditLogger(run_dir / "AUDIT.jsonl")
    audit.log(
        AuditEvent(
            run_id=run_id,
            event_type="adapter_invocation",
            adapter="github-identity",
            request_meta={"source_url": "https://api.github.com/users/jdoe88"},
            outcome="succeeded",
        )
    )
    audit.log(
        AuditEvent(
            run_id=run_id,
            event_type="cascade_run_finished",
            request_meta={"stop_reason": "saturated"},
            outcome="completed",
        )
    )
    return data, str(run_id), run_id


def test_generate_dossier_reads_artifacts_and_writes_markdown(tmp_path: Path) -> None:
    data, run_id, _ = _run_artifacts(tmp_path)
    client = _FakeClient()

    dossier = generate_dossier(run_id, str(data), client=client, echo=False)

    assert dossier.startswith("# Dossier")
    output = data / "runs" / run_id / "dossier.md"
    assert output.read_text(encoding="utf-8").startswith("# Dossier")
    call = client.completions.calls[0]
    assert call["model"] == "llama3"
    system = call["messages"][0]["content"]
    user = call["messages"][1]["content"]
    assert "senior intelligence analyst" in system
    assert "adapter, source URL" in system
    assert "https://api.github.com/users/jdoe88" in user
    assert "github-identity" in user
    assert "text_embedding" in user
    assert "AUDIT.jsonl" in user
    assert '"hash"' in user
    assert "Evidence Gaps" in user


def test_generate_dossier_accepts_a_model_override(tmp_path: Path) -> None:
    data, run_id, _ = _run_artifacts(tmp_path)
    client = _FakeClient("dossier")

    generate_dossier(
        run_id, str(data), "http://localhost:11434/v1", model="phi3", client=client, echo=False
    )

    assert client.completions.calls[0]["model"] == "phi3"


def test_generate_dossier_fails_loudly_on_missing_graph(tmp_path: Path) -> None:
    data = tmp_path / "data"
    run_dir = data / "runs" / str(uuid4())
    run_dir.mkdir(parents=True)
    (run_dir / "resolution.json").write_text("{}", encoding="utf-8")
    (run_dir / "AUDIT.jsonl").write_text('{"seq": 1}\n', encoding="utf-8")

    with pytest.raises(FileNotFoundError, match="graph.json"):
        generate_dossier(run_dir.name, str(data), client=_FakeClient(), echo=False)


def test_parse_ask_query_variants() -> None:
    assert parse_ask_query(
        "Find the identity of the person behind username frost2233"
    ) == Seed(type=SeedType.USERNAME, value="frost2233")
    assert parse_ask_query("Look up reddit user frost2233") == Seed(
        type=SeedType.USERNAME, value="frost2233"
    )
    assert parse_ask_query("Check jane@example.com") == Seed(
        type=SeedType.EMAIL, value="jane@example.com"
    )
    assert parse_ask_query("Investigate https://github.com/jdoe") == Seed(
        type=SeedType.URL, value="https://github.com/jdoe"
    )
    assert parse_ask_query("domain: example.com") == Seed(
        type=SeedType.DOMAIN, value="example.com"
    )
    assert parse_ask_query("Find the person behind frost2233") == Seed(
        type=SeedType.USERNAME, value="frost2233"
    )


def test_cascade_artifacts_feed_dossier_generation(tmp_path: Path) -> None:
    from aletheia.cascade.runner import (
        CascadeRunConfig,
        fixture_observer,
        run_cascade,
    )

    fixture = tmp_path / "fixture.json"
    fixture.write_text(
        json.dumps(
            {
                "answers": {
                    "email:alice@example.com": {
                        "findings": [
                            {
                                "entity_type": "email",
                                "value": "alice@example.com",
                                "provenance": {
                                    "tool": "fixture-world",
                                    "confidence": 1.0,
                                    "adapter_version": "fixture-1",
                                },
                            }
                        ]
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    data = tmp_path / "data"
    outcome = run_cascade(
        CascadeRunConfig(
            data_root=data, seeds=[Seed(type=SeedType.EMAIL, value="alice@example.com")]
        ),
        observer=fixture_observer(fixture),
    )
    client = _FakeClient("# Cascade dossier")

    dossier = generate_dossier(str(outcome.run_id), str(data), client=client, echo=False)

    assert dossier == "# Cascade dossier"
    assert (data / "graphs" / str(outcome.run_id) / "graph.json").exists()
    assert (data / "runs" / str(outcome.run_id) / "resolution.json").exists()
    assert (data / "runs" / str(outcome.run_id) / "dossier.md").exists()
    user_prompt = client.completions.calls[0]["messages"][1]["content"]
    assert '"valid": true' in user_prompt


def test_cli_ask_accepts_llm_options() -> None:
    args = build_parser().parse_args(
        [
            "ask",
            "Find the person behind username frost2233",
            "--llm-model",
            "phi3",
            "--llm-url",
            "http://127.0.0.1:11434/v1",
        ]
    )
    assert args.llm_model == "phi3"
    assert args.llm_url == "http://127.0.0.1:11434/v1"


def test_cli_ask_runs_cascade_then_calls_dossier(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    fixture = tmp_path / "fixture.json"
    fixture.write_text(
        json.dumps(
            {
                "answers": {
                    "username:frost2233": {
                        "findings": [
                            {
                                "entity_type": "social_account",
                                "value": "https://github.com/frost2233",
                                "attributes": {
                                    "platform": "github",
                                    "username": "frost2233",
                                },
                                "provenance": {
                                    "tool": "fixture-world",
                                    "confidence": 1.0,
                                    "adapter_version": "fixture-1",
                                },
                            }
                        ]
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    from aletheia.reporting import dossier as dossier_module

    calls: list[tuple[str, str, str, str | None]] = []

    def fake_generate(
        run_id: str,
        data_dir: str,
        llm_url: str,
        *,
        model: str | None = None,
        **kwargs,
    ) -> str:
        calls.append((run_id, data_dir, llm_url, model))
        return "# Synthetic dossier"

    monkeypatch.setattr(dossier_module, "generate_dossier", fake_generate)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "aletheia",
            "ask",
            "Find the person behind username frost2233",
            "--fixture",
            str(fixture),
            "--data-dir",
            str(tmp_path / "ask-data"),
            "--llm-model",
            "phi3",
        ],
    )

    main()
    out = capsys.readouterr().out
    assert "seed=username:frost2233" in out
    assert "stop_reason=saturated" in out
    assert calls and calls[0][1] == str(tmp_path / "ask-data")
    assert calls[0][3] == "phi3"
    run_id = calls[0][0]
    assert (tmp_path / "ask-data" / "graphs" / run_id / "graph.json").exists()
    assert (tmp_path / "ask-data" / "runs" / run_id / "resolution.json").exists()
