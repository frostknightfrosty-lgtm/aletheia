"""Phase 18.3 semantic profile-linking tests.

No model download and no network: the sentence model is replaced with a
fixed-vector stub, exactly at the lazy import boundary used in production.
"""

from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from aletheia.cascade import semantic
from aletheia.core.graph import Graph
from aletheia.core.models import EntityType, RelationshipType
from aletheia.phase2.resolution import EntityResolver


class _StubSentenceTransformer:
    instances: list["_StubSentenceTransformer"] = []

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self.encode_calls: list[list[str]] = []
        self.instances.append(self)

    def encode(self, texts, **kwargs):
        self.encode_calls.append(list(texts))
        vectors: list[list[float]] = []
        for text in texts:
            lowered = text.casefold()
            if "distributed" in lowered:
                vectors.append([1.0, 0.0, 0.0])
            elif "gardening" in lowered:
                vectors.append([0.0, 1.0, 0.0])
            else:
                vectors.append([0.0, 0.0, 1.0])
        return vectors


@pytest.fixture
def stub_model(monkeypatch):
    semantic.reset_text_embedding_model()
    _StubSentenceTransformer.instances.clear()
    monkeypatch.setitem(
        sys.modules,
        "sentence_transformers",
        SimpleNamespace(SentenceTransformer=_StubSentenceTransformer),
    )
    yield _StubSentenceTransformer
    semantic.reset_text_embedding_model()


def _profile(
    graph: Graph,
    value: str,
    platform: str,
    bio: str | None,
) -> None:
    attributes = {"platform": platform, "username": value.rsplit("/", 1)[-1]}
    if bio is not None:
        attributes["bio"] = bio
    graph.upsert_entity(EntityType.SOCIAL_ACCOUNT, value, attributes)


def test_lazy_model_is_loaded_once_and_semantic_link_is_confirmed(stub_model) -> None:
    graph = Graph()
    _profile(
        graph,
        "https://github.com/jdoe88",
        "github",
        "Backend engineer working on distributed systems and public data.",
    )
    _profile(
        graph,
        "https://reddit.com/user/john.doe",
        "reddit",
        "I build distributed systems and write about backend engineering.",
    )

    resolver = EntityResolver(fetch_avatars=False)
    assert stub_model.instances == []  # construction/import must not load the model
    assert resolver.resolve(graph) == []

    assert len(stub_model.instances) == 1
    assert stub_model.instances[0].model_name == semantic.TEXT_EMBEDDING_MODEL
    links = [link for link in resolver.last_confirmed_links if link.source == "text_embedding"]
    assert len(links) == 1
    assert links[0].confidence == 0.85
    assert links[0].metrics["cosine_similarity"] >= semantic.TEXT_EMBEDDING_THRESHOLD
    assert resolver.last_semantic_error is None

    edge = next(
        edge
        for edge in graph.edges.values()
        if edge.relationship is RelationshipType.SAME_AS_CONFIRMED
    )
    assert edge.attributes["source"] == "text_embedding"
    assert edge.provenance.tool == "aletheia.semantic_profile_linker"


def test_low_similarity_bios_do_not_create_an_edge(stub_model) -> None:
    graph = Graph()
    _profile(
        graph,
        "https://github.com/jdoe88",
        "github",
        "Backend engineer working on distributed systems.",
    )
    _profile(
        graph,
        "https://reddit.com/user/gardener",
        "reddit",
        "Gardening, seed saving, and local community gardens.",
    )

    resolver = EntityResolver(fetch_avatars=False)
    resolver.resolve(graph)

    assert resolver.last_confirmed_links == []
    assert resolver.last_semantic_error is None
    assert not any(
        edge.relationship is RelationshipType.SAME_AS_CONFIRMED
        for edge in graph.edges.values()
    )


def test_empty_short_and_non_latin_bios_skip_the_model(stub_model) -> None:
    graph = Graph()
    _profile(graph, "https://github.com/empty", "github", "")
    _profile(graph, "https://reddit.com/user/short", "reddit", "too short")
    _profile(
        graph,
        "https://example.com/users/ivan",
        "forum",
        "Иван пишет о распределённых системах и открытых данных.",
    )

    resolver = EntityResolver(fetch_avatars=False)
    resolver.resolve(graph)

    assert stub_model.instances == []
    assert resolver.last_semantic_error is None


def test_embedding_failure_is_recorded_without_breaking_resolution() -> None:
    graph = Graph()
    _profile(
        graph,
        "https://github.com/jdoe88",
        "github",
        "Backend engineer working on distributed systems.",
    )
    _profile(
        graph,
        "https://reddit.com/user/john.doe",
        "reddit",
        "I build distributed systems and write about backend engineering.",
    )

    def broken_embedder(texts):
        raise RuntimeError("model unavailable")

    resolver = EntityResolver(fetch_avatars=False, text_embedder=broken_embedder)
    resolver.resolve(graph)

    assert resolver.last_confirmed_links == []
    assert resolver.last_semantic_error == "model unavailable"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("", False),
        ("short", False),
        ("123456789012345", False),
        ("A useful ten+ character bio.", True),
        ("Ingénieur systèmes distribués", True),
        ("Иван пишет о данных", False),
        ("東京で働いています", False),
    ],
)
def test_usable_bio_filter(text: str, expected: bool) -> None:
    assert semantic.usable_bio(text) is expected
