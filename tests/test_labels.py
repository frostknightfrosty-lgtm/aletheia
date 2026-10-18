"""Tests for the confirmation label store (P17.7)."""

from __future__ import annotations

import pytest

from aletheia.core.calibration import Calibrator
from aletheia.core.labels import ConfirmLabel, LabelStore


def test_add_and_round_trip(tmp_path):
    store = LabelStore(tmp_path / "labels.jsonl")
    store.add(
        case_id="c1",
        cluster_id="cluster-a",
        label=ConfirmLabel.MINE,
        score=12.5,
        note="owner confirmed",
    )
    reopened = LabelStore(tmp_path / "labels.jsonl")
    records = reopened.all()
    assert len(records) == 1
    assert records[0].label is ConfirmLabel.MINE
    assert records[0].score == 12.5
    assert records[0].note == "owner confirmed"


def test_validation(tmp_path):
    store = LabelStore(tmp_path / "labels.jsonl")
    with pytest.raises(ValueError):
        store.add(case_id="c1", cluster_id="x", label="maybe")
    with pytest.raises(ValueError):
        store.add(case_id="", cluster_id="x", label=ConfirmLabel.MINE)
    with pytest.raises(ValueError):
        store.add(case_id="c1", cluster_id="", label=ConfirmLabel.MINE)


def test_resolved_latest_wins(tmp_path):
    store = LabelStore(tmp_path / "labels.jsonl")
    store.add(case_id="c1", cluster_id="a", label=ConfirmLabel.UNSURE)
    store.add(case_id="c1", cluster_id="a", label=ConfirmLabel.MINE, score=3.0)
    store.add(case_id="c1", cluster_id="b", label=ConfirmLabel.NOT_MINE, score=1.0)
    resolved = store.resolved()
    assert resolved[("c1", "a")].label is ConfirmLabel.MINE
    assert store.counts() == {"mine": 1, "not_mine": 1, "unsure": 0}


def test_training_pairs_exclude_unsure_and_scoreless(tmp_path):
    store = LabelStore(tmp_path / "labels.jsonl")
    store.add(case_id="c1", cluster_id="mine", label=ConfirmLabel.MINE, score=9.0)
    store.add(case_id="c1", cluster_id="not", label=ConfirmLabel.NOT_MINE, score=1.5)
    store.add(case_id="c1", cluster_id="unsure", label=ConfirmLabel.UNSURE, score=5.0)
    store.add(case_id="c1", cluster_id="scoreless", label=ConfirmLabel.MINE)
    assert store.training_pairs() == [(9.0, 1), (1.5, 0)]


def test_training_pairs_feed_the_calibrator(tmp_path):
    store = LabelStore(tmp_path / "labels.jsonl")
    # Overlapping scores, as real calibration data is: mine tends higher, but
    # the classes are not perfectly separable (a perfectly separable sample
    # diverges under the Phase-13 Platt fit — noted in the campaign log).
    pairs = [
        (0.5, ConfirmLabel.NOT_MINE),
        (0.6, ConfirmLabel.MINE),
        (0.7, ConfirmLabel.NOT_MINE),
        (0.8, ConfirmLabel.MINE),
        (0.9, ConfirmLabel.MINE),
        (1.0, ConfirmLabel.NOT_MINE),
        (1.1, ConfirmLabel.MINE),
        (1.2, ConfirmLabel.MINE),
    ]
    for index, (score, label) in enumerate(pairs):
        store.add(case_id="c1", cluster_id=f"c{index}", label=label, score=score)
    calibrator = Calibrator()
    assert calibrator.trained is False
    calibrator.fit(store.training_pairs())
    assert calibrator.trained is True
    assert 0.0 <= calibrator.predict(0.5) <= 1.0
    assert calibrator.predict(1.2) > calibrator.predict(0.5)
