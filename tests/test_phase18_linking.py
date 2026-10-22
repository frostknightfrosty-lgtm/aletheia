"""Phase 18.1 profile linking tests (avatar pHash, network, cadence, review).

No network and no Docker: the avatar fetcher and adapter-refetch hook are
injected, exactly as the live wiring does at the resolver boundary.
"""

from __future__ import annotations

import builtins
import json
import sys
from pathlib import Path

from aletheia.cascade.claims import claim_from_finding
from aletheia.cascade.engine import CascadeEngine, Observation
from aletheia.cascade.interactive import (
    CandidateMatch,
    append_calibration_pair,
    format_candidate_prompt,
    interactive_reviewer,
)
from aletheia.cascade.profile_linking import (
    AVATAR_CONFIDENCE,
    NETWORK_CONFIDENCE,
    ProfileLinker,
)
from aletheia.cascade.scheduler import SchedulerPolicy
from aletheia.cascade.scoring import (
    TEMPORAL_CONFIDENCE_BOOST,
    apply_temporal_boost,
    compare_activity_histograms,
    extract_active_hours,
)
from aletheia.cli.main import build_parser, main
from aletheia.core.graph import Graph
from aletheia.core.models import (
    EntityType,
    Finding,
    IdentityTier,
    Provenance,
    RelationshipType,
    SeedType,
)
from aletheia.phase2.resolution import EntityResolver


def _ppm() -> bytes:
    return b"P6\n8 8\n255\n" + bytes(
        (x * 31 + y * 7) % 256 for y in range(8) for x in range(8) for _ in range(3)
    )


def _finding(
    entity_type: EntityType,
    value: str,
    *,
    attributes: dict[str, object] | None = None,
    tool: str = "world",
) -> Finding:
    return Finding(
        entity_type=entity_type,
        value=value,
        attributes=dict(attributes or {}),
        provenance=Provenance(tool=tool, confidence=1.0, adapter_version="fixture-1"),
    )


def _claim(
    entity_type: EntityType,
    value: str,
    *,
    attributes: dict[str, object] | None = None,
    tool: str = "seed",
):
    return claim_from_finding(
        _finding(entity_type, value, attributes=attributes, tool=tool)
    )


def _timestamps() -> list[str]:
    return [
        "2026-01-01T09:00:00Z",
        "2026-01-02T10:00:00Z",
        "2026-01-03T11:00:00Z",
    ]


def test_phash_distance_confirms_profile_edge() -> None:
    graph = Graph()
    left = graph.upsert_entity(
        EntityType.SOCIAL_ACCOUNT,
        "https://github.com/jdoe88",
        {"platform": "github", "username": "jdoe88", "avatar_phash": "0123456789abcdef"},
    )
    right = graph.upsert_entity(
        EntityType.SOCIAL_ACCOUNT,
        "https://reddit.com/user/john.doe",
        {
            "platform": "reddit",
            "username": "john.doe",
            "avatar_phash": "0123456789abcdee",  # Hamming distance 1
        },
    )

    resolver = EntityResolver(fetch_avatars=False)
    assert resolver.resolve(graph) == []

    links = resolver.last_confirmed_links
    assert len(links) == 1
    assert links[0].source == "avatar_phash"
    assert links[0].confidence == AVATAR_CONFIDENCE
    edge = next(iter(graph.edges.values()))
    assert edge.relationship is RelationshipType.SAME_AS_CONFIRMED
    assert edge.confidence == 0.95
    assert edge.attributes["source"] == "avatar_phash"
    assert {edge.source_entity_id, edge.target_entity_id} == {
        left.entity_id,
        right.entity_id,
    }


def test_missing_avatar_triggers_adapter_refetch_then_phash_match() -> None:
    graph = Graph()
    graph.upsert_entity(
        EntityType.URL,
        "https://github.com/jdoe88",
        {"platform": "github", "username": "jdoe88"},
    )
    graph.upsert_entity(
        EntityType.URL,
        "https://reddit.com/user/john.doe",
        {"platform": "reddit", "username": "john.doe"},
    )
    enrichment_calls: list[str] = []
    avatar_fetches: list[str] = []

    def enrich(entity) -> dict[str, object]:
        username = entity.attributes["username"]
        enrichment_calls.append(username)
        return {"avatar_url": f"https://cdn.example/{username}.ppm"}

    def fetch(url: str) -> bytes:
        avatar_fetches.append(url)
        return _ppm()

    resolver = EntityResolver(profile_enricher=enrich, avatar_fetcher=fetch)
    assert resolver.resolve(graph) == []

    assert sorted(enrichment_calls) == ["jdoe88", "john.doe"]
    assert sorted(avatar_fetches) == [
        "https://cdn.example/jdoe88.ppm",
        "https://cdn.example/john.doe.ppm",
    ]
    assert [link.source for link in resolver.last_confirmed_links] == ["avatar_phash"]


def test_network_jaccard_confirms_profile_edge() -> None:
    graph = Graph()
    graph.upsert_entity(
        EntityType.SOCIAL_ACCOUNT,
        "https://github.com/jdoe88",
        {
            "platform": "github",
            "username": "jdoe88",
            "connections": ["alice", "bob", "carol"],
        },
    )
    graph.upsert_entity(
        EntityType.SOCIAL_ACCOUNT,
        "https://reddit.com/user/john.doe",
        {
            "platform": "reddit",
            "username": "john.doe",
            "connections": ["alice", "bob", "dave"],
        },
    )

    resolver = EntityResolver(fetch_avatars=False)
    resolver.resolve(graph)

    assert len(resolver.last_confirmed_links) == 1
    link = resolver.last_confirmed_links[0]
    assert link.source == "network_overlap"
    assert link.confidence == NETWORK_CONFIDENCE
    assert link.metrics["jaccard"] == 0.5


def test_temporal_cadence_requires_multiple_samples_and_boosts_fuzzy_match() -> None:
    timestamps = _timestamps()
    cadence = compare_activity_histograms(timestamps, timestamps)
    assert cadence.significant is True
    assert cadence.overlap == 1.0
    assert extract_active_hours(timestamps) == (9, 10, 11)

    boosted, _ = apply_temporal_boost(0.80, timestamps, timestamps)
    assert boosted == 0.95

    single = compare_activity_histograms(timestamps[:1], timestamps[:1])
    assert single.significant is False
    assert single.boost == 0.0

    graph = Graph()
    graph.upsert_entity(EntityType.USERNAME, "alice", {"activity_timestamps": timestamps})
    graph.upsert_entity(EntityType.USERNAME, "alise", {"activity_timestamps": timestamps})
    candidates = EntityResolver(
        candidate_threshold=0.88, fetch_avatars=False
    ).resolve(graph)
    assert len(candidates) == 1
    assert candidates[0].temporal_boost == TEMPORAL_CONFIDENCE_BOOST
    assert candidates[0].score >= 0.88


def test_avatar_link_triggers_cascade_expansion() -> None:
    root_username = _claim(EntityType.USERNAME, "jdoe88")
    root_profile = _claim(
        EntityType.SOCIAL_ACCOUNT,
        "https://github.com/jdoe88",
        attributes={
            "platform": "github",
            "username": "jdoe88",
            "avatar_phash": "0123456789abcdef",
        },
    )
    world = {
        (SeedType.USERNAME, "jdoe88"): Observation(
            findings=(
                _finding(
                    EntityType.SOCIAL_ACCOUNT,
                    "https://www.reddit.com/user/john.doe/",
                    attributes={
                        "platform": "reddit",
                        "username": "john.doe",
                        "avatar_phash": "0123456789abcdee",
                    },
                ),
            )
        ),
        (SeedType.URL, "https://www.reddit.com/user/john.doe/"): Observation(
            findings=(_finding(EntityType.USERNAME, "john.doe"),)
        ),
    }
    calls: list[tuple[SeedType, str]] = []

    def observer(seed) -> Observation:
        calls.append((seed.type, seed.value))
        return world.get((seed.type, seed.value), Observation())

    result = CascadeEngine(observer, policy=SchedulerPolicy()).run(
        [root_username, root_profile]
    )

    reddit = next(
        case
        for case in result.candidates
        if case.claim.value == "https://www.reddit.com/user/john.doe/"
    )
    assert reddit.accepted is True
    assert reddit.tier is IdentityTier.CONFIRMED
    assert any(
        link.source == "avatar_phash"
        and link.relationship is RelationshipType.SAME_AS_CONFIRMED
        for link in result.profile_links
    )
    assert (SeedType.URL, "https://www.reddit.com/user/john.doe/") in calls


def test_interactive_no_marks_candidate_excluded() -> None:
    root_profile = _claim(
        EntityType.SOCIAL_ACCOUNT,
        "https://github.com/jdoe88",
        attributes={
            "platform": "github",
            "username": "jdoe88",
            "display_name": "John Doe",
            "activity_timestamps": _timestamps(),
        },
    )
    world = {
        (SeedType.URL, "https://github.com/jdoe88"): Observation(
            findings=(
                _finding(
                    EntityType.SOCIAL_ACCOUNT,
                    "https://www.reddit.com/user/john.doe/",
                    attributes={
                        "platform": "reddit",
                        "username": "john.doe",
                        "display_name": "J Doe",
                        "activity_timestamps": _timestamps(),
                    },
                ),
            )
        ),
    }

    def observer(seed) -> Observation:
        return world.get((seed.type, seed.value), Observation())

    result = CascadeEngine(
        observer,
        policy=SchedulerPolicy(),
        review_callback=lambda _match: "n",
    ).run([root_profile])

    reddit = result.candidates[0]
    assert reddit.operator_label == "excluded"
    assert reddit.tier is IdentityTier.EXCLUDED
    assert reddit.accepted is False
    assert any(
        link.source == "interactive_label"
        and link.relationship is RelationshipType.SAME_AS_EXCLUDED
        for link in result.profile_links
    )


def test_interactive_review_prompts_and_records_labels(tmp_path: Path) -> None:
    subject = _claim(
        EntityType.SOCIAL_ACCOUNT,
        "https://github.com/jdoe88",
        attributes={"platform": "github", "username": "jdoe88"},
    )
    candidate = _claim(
        EntityType.SOCIAL_ACCOUNT,
        "https://reddit.com/user/john.doe",
        attributes={"platform": "reddit", "username": "john.doe"},
    )
    match = CandidateMatch(subject, candidate, confidence=0.80)
    assert (
        format_candidate_prompt(match)
        == '[?] Candidate Match: "jdoe88" (GitHub) == "john.doe" (Reddit). '
        "Are they the same person? [y/N/s(kip)]"
    )

    fixture = tmp_path / "calibration_pairs.json"
    reviewer, recorded = interactive_reviewer(fixture, input_func=lambda _: "y")
    assert reviewer(match) == "confirmed"
    assert len(recorded) == 1

    payload = json.loads(fixture.read_text(encoding="utf-8"))
    assert payload["pairs"][-1]["score"] == 0.80
    assert payload["pairs"][-1]["label"] == 1
    assert payload["pairs"][-1]["source"] == "cascade_interactive"

    entry = append_calibration_pair(
        fixture,
        score=0.75,
        label=0,
        note="synthetic negative for the test",
        left="jdoe88",
        right="john.doe",
    )
    assert entry["label"] == 0
    assert len(json.loads(fixture.read_text(encoding="utf-8"))["pairs"]) == 2


def test_cli_accepts_interactive_flag_before_or_after_run() -> None:
    parser = build_parser()
    assert parser.parse_args(
        ["cascade", "--interactive", "run", "--seed", "username:jdoe88"]
    ).interactive is True
    assert parser.parse_args(
        ["cascade", "run", "--seed", "username:jdoe88", "--interactive"]
    ).interactive is True


def test_cli_interactive_y_records_confirmed_pair(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    fixture = tmp_path / "fixture.json"
    profile = {
        "provenance": {
            "tool": "fixture-world",
            "confidence": 1.0,
            "adapter_version": "fixture-1",
        }
    }
    fixture.write_text(
        json.dumps(
            {
                "answers": {
                    "username:jdoe88": {
                        "findings": [
                            {
                                **profile,
                                "entity_type": "social_account",
                                "value": "https://github.com/jdoe88",
                                "attributes": {
                                    "platform": "github",
                                    "username": "jdoe88",
                                    "display_name": "John Doe",
                                    "activity_timestamps": _timestamps(),
                                },
                            }
                        ]
                    },
                    "url:https://github.com/jdoe88": {
                        "findings": [
                            {
                                **profile,
                                "entity_type": "social_account",
                                "value": "https://www.reddit.com/user/john.doe/",
                                "attributes": {
                                    "platform": "reddit",
                                    "username": "john.doe",
                                    "display_name": "J Doe",
                                    "activity_timestamps": _timestamps(),
                                },
                            }
                        ]
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    pairs = tmp_path / "calibration_pairs.json"
    prompts: list[str] = []

    def fake_input(prompt: str) -> str:
        prompts.append(prompt)
        return "y"

    monkeypatch.setattr(builtins, "input", fake_input)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "aletheia",
            "cascade",
            "--interactive",
            "run",
            "--seed",
            "username:jdoe88",
            "--fixture",
            str(fixture),
            "--data-dir",
            str(tmp_path / "data"),
            "--calibration-pairs",
            str(pairs),
        ],
    )
    main()

    assert prompts == [
        '[?] Candidate Match: "jdoe88" (GitHub) == "john.doe" (Reddit). '
        "Are they the same person? [y/N/s(kip)]"
    ]
    assert "labels_recorded=1" in capsys.readouterr().out
    payload = json.loads(pairs.read_text(encoding="utf-8"))
    assert payload["pairs"][-1]["label"] == 1
    assert payload["pairs"][-1]["source"] == "cascade_interactive"


def test_profile_linker_uses_jaccard_not_raw_overlap() -> None:
    linker = ProfileLinker(fetch_avatars=False)
    left = type(
        "Entity",
        (),
        {
            "entity_id": None,
            "canonical_value": "left",
            "attributes": {
                "platform": "github",
                "username": "left",
                "connections": ["a", "b", "c"],
            },
        },
    )()
    right = type(
        "Entity",
        (),
        {
            "entity_id": None,
            "canonical_value": "right",
            "attributes": {
                "platform": "reddit",
                "username": "right",
                "connections": ["a", "b", "d"],
            },
        },
    )()
    # A raw overlap of 2/3 would pass an naive threshold; Jaccard is 2/4.
    left_profile = linker.prepare(left)
    right_profile = linker.prepare(right)
    network = linker.network_overlap(left_profile, right_profile)
    assert network.jaccard == 0.5
    assert network.significant is True
