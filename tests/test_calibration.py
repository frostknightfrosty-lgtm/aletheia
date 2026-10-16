"""Tests for the Phase 13 score-calibration component.

Platt scaling and isotonic regression are real fits (Newton-Raphson and PAV), so
these tests assert the mathematical properties that make them calibrators:
monotonicity, bounded probabilities, correct handling of degenerate input, and an
honest ``trained`` flag. The resolver integration is checked through the
``SAME_AS_CANDIDATE`` edge attribute, which is what a consumer actually reads.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from aletheia.core.calibration import (
    MIN_LABELED_PAIRS,
    CalibrationError,
    Calibrator,
    IsotonicRegression,
    PlattScaling,
    calibrator_from_file,
    load_pairs,
)
from aletheia.core.graph import Graph
from aletheia.core.models import EntityType
from aletheia.phase2.resolution import EntityResolver

FIXTURE = Path(__file__).with_name("fixtures") / "calibration_pairs.json"

GRID = [round(0.50 + 0.02 * i, 4) for i in range(26)]


# -- fixture -------------------------------------------------------------------


def test_fixture_is_labelled_with_both_classes():
    pairs = load_pairs(FIXTURE)
    assert len(pairs) >= MIN_LABELED_PAIRS
    labels = {int(pair["label"]) for pair in pairs}
    assert labels == {0, 1}
    for pair in pairs:
        assert 0.0 <= float(pair["score"]) <= 1.0


# -- Platt scaling -------------------------------------------------------------


def test_platt_fit_is_monotone_and_bounded():
    calibrator = calibrator_from_file(FIXTURE, method="platt")
    assert calibrator.trained
    predictions = [calibrator.predict(score) for score in GRID]
    assert predictions == sorted(predictions)
    assert all(0.0 <= p <= 1.0 for p in predictions)


def test_platt_prediction_is_the_fitted_logistic():
    model = PlattScaling().fit([0.1, 0.4, 0.6, 0.9], [0, 0, 1, 1])
    assert model.fitted
    for score in (0.2, 0.5, 0.8):
        expected = 1.0 / (1.0 + math.exp(-(model.slope * score + model.intercept)))
        assert model.predict(score) == pytest.approx(expected, abs=1e-12)


def test_platt_requires_both_labels():
    with pytest.raises(CalibrationError):
        PlattScaling().fit([0.1, 0.2, 0.3], [1, 1, 1])


def test_platt_predict_before_fit_raises():
    with pytest.raises(CalibrationError):
        PlattScaling().predict(0.9)


# -- isotonic regression -------------------------------------------------------


def test_isotonic_fit_is_monotone():
    model = IsotonicRegression().fit(
        [0.99, 0.60, 0.93, 0.70, 0.85, 0.55], [1, 0, 1, 0, 0, 0]
    )
    predictions = [model.predict(score) for score in GRID]
    assert predictions == sorted(predictions)
    assert all(0.0 <= p <= 1.0 for p in predictions)


def test_isotonic_pool_adjacent_violators_averages_a_conflict():
    # Same score, opposite labels -> a single block at the mean.
    model = IsotonicRegression().fit([0.5, 0.5], [1, 0])
    assert model.predict(0.5) == pytest.approx(0.5)


def test_isotonic_clips_out_of_range_inputs():
    model = IsotonicRegression().fit([0.2, 0.4, 0.6, 0.8], [0, 0, 1, 1])
    assert model.predict(-1.0) == model.predict(0.2)
    assert model.predict(2.0) == model.predict(0.8)


# -- Calibrator: honesty about training data -----------------------------------


def test_calibrator_is_untrained_below_min_pairs():
    calibrator = Calibrator("platt").fit([(0.9, 1), (0.2, 0)])
    assert calibrator.trained is False
    with pytest.raises(CalibrationError):
        calibrator.predict(0.9)


def test_calibrator_is_untrained_without_both_labels():
    calibrator = Calibrator("platt").fit([(0.9, 1)] * (MIN_LABELED_PAIRS + 2))
    assert calibrator.trained is False


def test_calibrator_rejects_unknown_method():
    with pytest.raises(CalibrationError):
        Calibrator("magic")


def test_calibrator_rejects_malformed_pairs():
    with pytest.raises(CalibrationError):
        Calibrator("platt").fit([("not-a-number", 1)] * 8)
    with pytest.raises(CalibrationError):
        Calibrator("platt").fit([(0.5, 2)] * 8)


def test_calibrator_ranks_positive_scores_above_negative_scores():
    calibrator = calibrator_from_file(FIXTURE)
    pairs = load_pairs(FIXTURE)
    positives = [float(p["score"]) for p in pairs if int(p["label"]) == 1]
    negatives = [float(p["score"]) for p in pairs if int(p["label"]) == 0]
    mean_pos = sum(calibrator.predict(s) for s in positives) / len(positives)
    mean_neg = sum(calibrator.predict(s) for s in negatives) / len(negatives)
    assert mean_pos > mean_neg


# -- serialization round-trip --------------------------------------------------


def test_platt_round_trips_through_dict():
    original = calibrator_from_file(FIXTURE, method="platt")
    restored = Calibrator.from_dict(original.to_dict())
    assert restored.trained
    assert restored.method == "platt"
    for score in GRID:
        assert restored.predict(score) == pytest.approx(original.predict(score))


def test_isotonic_round_trips_through_dict():
    original = calibrator_from_file(FIXTURE, method="isotonic")
    restored = Calibrator.from_dict(original.to_dict())
    assert restored.trained
    assert restored.method == "isotonic"
    for score in GRID:
        assert restored.predict(score) == pytest.approx(original.predict(score))


# -- resolver integration ------------------------------------------------------


def _resolution_edge(graph: Graph):
    edges = [e for e in graph.edges.values() if e.relationship.value == "same_as_candidate"]
    assert len(edges) == 1, f"expected exactly one candidate edge, got {len(edges)}"
    return edges[0]


def test_resolver_reports_uncalibrated_without_training_data():
    graph = Graph()
    graph.upsert_entity(EntityType.USERNAME, "alice")
    graph.upsert_entity(EntityType.USERNAME, "alica")
    candidates = EntityResolver(candidate_threshold=0.75).resolve(graph)
    assert candidates
    resolution = _resolution_edge(graph).attributes["resolution"]
    assert resolution["calibrated"] is False
    assert resolution["calibrated_probability"] is None
    assert any("no_trained_calibrator" in note for note in resolution["explanation"])


def test_resolver_reports_uncalibrated_with_an_untrained_calibrator():
    graph = Graph()
    graph.upsert_entity(EntityType.USERNAME, "alice")
    graph.upsert_entity(EntityType.USERNAME, "alica")
    EntityResolver(candidate_threshold=0.75, calibrator=Calibrator("platt")).resolve(graph)
    resolution = _resolution_edge(graph).attributes["resolution"]
    assert resolution["calibrated"] is False
    assert resolution["calibrated_probability"] is None


def test_resolver_reports_calibrated_probability_with_trained_calibrator():
    calibrator = calibrator_from_file(FIXTURE)
    graph = Graph()
    graph.upsert_entity(EntityType.USERNAME, "alice")
    graph.upsert_entity(EntityType.USERNAME, "alica")
    candidates = EntityResolver(candidate_threshold=0.75, calibrator=calibrator).resolve(graph)
    assert len(candidates) == 1
    edge = _resolution_edge(graph)
    resolution = edge.attributes["resolution"]
    assert resolution["calibrated"] is True
    assert 0.0 <= resolution["calibrated_probability"] <= 1.0
    assert candidates[0].calibrated is True
    assert candidates[0].calibrated_probability == resolution["calibrated_probability"]
    # The raw similarity score is preserved alongside the calibrated probability.
    assert resolution["score"] == candidates[0].score
