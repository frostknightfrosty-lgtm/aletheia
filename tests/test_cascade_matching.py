"""Tests for the pure matchers (P17.4): strings, phonetics, names, graph, time."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from aletheia.cascade.matching import (
    era_coherence,
    fold_diacritics,
    idf_token_overlap,
    jaro_winkler,
    levenshtein_similarity,
    mutual_link_overlap,
    name_variants,
    names_equivalent,
    overlap_ratio,
    phonetic_key,
    recency_decay,
    set_overlap,
    shared_values,
    soundex,
    token_set_ratio,
    tokenize,
    transliterate,
)


def test_soundex_matches_published_nara_vectors():
    assert soundex("Robert") == "R163"
    assert soundex("Rupert") == "R163"
    assert soundex("Rubin") == "R150"
    assert soundex("Ashcraft") == "A261"
    assert soundex("Tymczak") == "T522"
    assert soundex("Pfister") == "P236"
    assert soundex("Honeyman") == "H555"
    assert soundex("") == ""
    assert soundex("1234") == ""


def test_phonetic_key_folds_diacritics_first():
    assert phonetic_key("M\u00fcller") == soundex("muller") == "M460"
    assert phonetic_key("Zoe") == "Z000"


def test_fold_diacritics_normalizes_typography():
    assert fold_diacritics("Jos\u00e9") == "jose"
    assert fold_diacritics("M\u00fcnchen") == "munchen"
    assert fold_diacritics("O\u2019Brien") == "o'brien"
    assert fold_diacritics("M\u00fcller\u200b") == "muller"


def test_transliterate_cyrillic_and_latin():
    assert transliterate("\u041f\u0440\u0438\u0432\u0435\u0442") == "privet"
    assert transliterate("\u042e\u043b\u044f") == "yulya"
    assert transliterate("Jos\u00e9") == "jose"


def test_jaro_winkler_and_levenshtein_bounds():
    assert jaro_winkler("martha", "martha") == 1.0
    assert jaro_winkler("martha", "marhta") >= 0.9
    assert levenshtein_similarity("abc", "abc") == 1.0
    assert levenshtein_similarity("abc", "abd") == pytest.approx(2 / 3)


def test_token_set_ratio_treats_subset_as_identical():
    assert token_set_ratio("alice smith", "alice") == 1.0
    assert token_set_ratio("alice smith", "bob jones") < 0.5


def test_tokenize_keeps_inner_apostrophes_and_strips_noise():
    assert tokenize("Alice von Example") == ["alice", "von", "example"]
    assert tokenize("O'Brien, Alice") == ["o'brien", "alice"]
    assert tokenize("  ...  ") == []


def test_idf_token_overlap_weights_rare_tokens_more():
    idf = {"alice": 5.0, "smith": 1.0}
    overlap = idf_token_overlap("alice smith", "alice jones", idf)
    assert overlap == pytest.approx(5.0 / 7.0)
    assert idf_token_overlap("", "", idf) == 0.0


def test_name_variants_and_equivalence():
    variants = name_variants("Robert Smith")
    assert "bob smith" in variants
    assert "rob smith" in variants
    assert names_equivalent("Bob Smith", "Robert Smith") is True
    assert names_equivalent("Katherine Jones", "Catherine Jones") is True
    assert names_equivalent("Alice Smith", "Robert Smith") is False
    assert name_variants("") == frozenset()


def test_set_overlap_and_shared_values():
    left = {"https://a.example", "https://b.example"}
    right = {"https://b.example", "https://c.example"}
    assert shared_values(left, right) == frozenset({"https://b.example"})
    assert mutual_link_overlap(left, right) == frozenset({"https://b.example"})
    assert set_overlap(left, right) == pytest.approx(1 / 3)
    assert set_overlap(set(), set()) == 0.0


def test_temporal_overlap_ratio_and_era_coherence():
    start = datetime(2020, 1, 1, tzinfo=timezone.utc)
    left_end = start + timedelta(hours=4)
    right_start = start + timedelta(hours=3)
    right_end = start + timedelta(hours=7)
    assert overlap_ratio(start, left_end, right_start, right_end) == pytest.approx(0.25)
    assert era_coherence(start, left_end, right_start, right_end) is True
    far_start = start + timedelta(days=400)
    assert overlap_ratio(start, left_end, far_start, far_start + timedelta(days=1)) == 0.0
    assert era_coherence(start, left_end, far_start, far_start + timedelta(days=1)) is False


def test_recency_decay_half_life_and_bounds():
    reference = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert recency_decay(reference, reference) == 1.0
    assert recency_decay(reference + timedelta(days=1), reference) == 1.0  # future clamps
    assert recency_decay(
        reference - timedelta(days=365), reference, half_life_days=365.0
    ) == pytest.approx(0.5)
    older = recency_decay(reference - timedelta(days=3650), reference, half_life_days=365.0)
    assert 0.0 < older < 0.1
    with pytest.raises(ValueError):
        recency_decay(reference, reference, half_life_days=0)
