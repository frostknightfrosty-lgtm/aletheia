"""Confidence-score calibration for entity-resolution matches (Phase 13).

The resolver's composite score (``0.65 * Jaro-Winkler + 0.35 * Levenshtein``,
see ``aletheia.phase2.resolution``) is a *similarity heuristic*, not a
probability: a score of 0.94 does not mean "94% likely to be the same entity".
This module fits a monotone map from that raw score to a calibrated probability
of a true match, using labelled matched/unmatched pairs:

* **Platt scaling** - a logistic (sigmoid) fit with Platt's target smoothing,
  trained by Newton-Raphson / IRLS on the (smoothed) log loss. Two parameters,
  ``slope`` and ``intercept``.
* **Isotonic regression** - a non-parametric monotone step fit computed with
  pool-adjacent-violators (PAV); no parametric form is assumed.

Only the standard library is used (``math``); the project installs no numeric
package and the fits here are tiny.

Honest limitation: a calibrator is only meaningful when it was fitted on enough
labelled pairs. ``Calibrator.trained`` stays ``False`` until ``fit`` has seen at
least ``MIN_LABELED_PAIRS`` pairs *with both labels present*, so callers never
report ``calibrated: true`` without training data.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

# A fit below this many labelled pairs, or a fit missing a class, is not trusted.
MIN_LABELED_PAIRS = 8

DEFAULT_METHOD = "platt"
METHODS = ("platt", "isotonic")


class CalibrationError(ValueError):
    """Raised for malformed training data or an untrained prediction."""


def _sigmoid(z: float) -> float:
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    exp_z = math.exp(z)
    return exp_z / (1.0 + exp_z)


def _clamp01(value: float) -> float:
    return 0.0 if value < 0.0 else 1.0 if value > 1.0 else value


def _as_pairs(pairs: Iterable[Any]) -> list[tuple[float, int]]:
    """Accept ``(score, label)`` tuples or ``{"score": .., "label": ..}`` dicts."""
    out: list[tuple[float, int]] = []
    for item in pairs:
        if isinstance(item, dict):
            score, label = item.get("score"), item.get("label")
        else:
            score, label = item[0], item[1]
        try:
            score_f = float(score)
        except (TypeError, ValueError) as exc:
            raise CalibrationError(f"score is not numeric: {score!r}") from exc
        if not math.isfinite(score_f):
            raise CalibrationError(f"score is not finite: {score!r}")
        label_i = int(label)
        if label_i not in (0, 1):
            raise CalibrationError(f"label must be 0 or 1, got {label!r}")
        out.append((score_f, label_i))
    return out


def _split(pairs: Sequence[tuple[float, int]]) -> tuple[list[float], list[int]]:
    return [score for score, _ in pairs], [label for _, label in pairs]


@dataclass
class PlattScaling:
    """Logistic calibration of a raw score to a probability.

    Fitted probability is ``sigmoid(slope * score + intercept)`` using Platt's
    target smoothing (``t+ = (N+ + 1) / (N+ + 2)``, ``t- = 1 / (N- + 2)``).
    """

    slope: float = 1.0
    intercept: float = 0.0
    fitted: bool = False

    def fit(self, scores: Sequence[float], labels: Sequence[int]) -> "PlattScaling":
        pairs = _as_pairs(list(zip(scores, labels)))
        if not pairs:
            raise CalibrationError("no training pairs")
        n_pos = sum(1 for _, label in pairs if label == 1)
        n_neg = len(pairs) - n_pos
        if n_pos == 0 or n_neg == 0:
            raise CalibrationError("Platt scaling needs both a positive and a negative label")
        # Platt's target smoothing avoids the degenerate 0/1 targets.
        hi = (n_pos + 1.0) / (n_pos + 2.0)
        lo = 1.0 / (n_neg + 2.0)
        targets = [hi if label == 1 else lo for _, label in pairs]
        xs = [score for score, _ in pairs]

        w, c = 1.0, -0.5  # p = sigmoid(w * score + c)
        reg = 1e-6  # tiny L2 keeps the Newton step well-defined
        for _ in range(100):
            g0 = g1 = h00 = h01 = h11 = 0.0
            for x, t in zip(xs, targets):
                p = _sigmoid(w * x + c)
                residual = p - t
                weight = p * (1.0 - p)
                g0 += residual * x
                g1 += residual
                h00 += weight * x * x
                h01 += weight * x
                h11 += weight
            g0 += reg * w
            g1 += reg * c
            h00 += reg
            h11 += reg
            det = h00 * h11 - h01 * h01
            if det == 0.0:
                break
            dw = (h11 * g0 - h01 * g1) / det
            dc = (-h01 * g0 + h00 * g1) / det
            w -= dw
            c -= dc
            if abs(dw) < 1e-12 and abs(dc) < 1e-12:
                break
        self.slope, self.intercept, self.fitted = w, c, True
        return self

    def predict(self, score: float) -> float:
        if not self.fitted:
            raise CalibrationError("PlattScaling is not fitted")
        return _clamp01(_sigmoid(self.slope * float(score) + self.intercept))

    def to_dict(self) -> dict[str, Any]:
        return {"kind": "platt", "slope": self.slope, "intercept": self.intercept, "fitted": self.fitted}

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "PlattScaling":
        return cls(slope=float(payload["slope"]), intercept=float(payload["intercept"]),
                   fitted=bool(payload.get("fitted", True)))


@dataclass
class IsotonicRegression:
    """Monotone step calibration via pool-adjacent-violators.

    ``blocks`` is a list of ``(x_high, value)`` breakpoints: for an input at or
    below ``x_high`` the prediction is that block's value (the last block applies
    above the final breakpoint, i.e. out-of-range inputs are clipped).
    """

    blocks: tuple[tuple[float, float], ...] = ()
    fitted: bool = False

    def fit(self, scores: Sequence[float], labels: Sequence[int]) -> "IsotonicRegression":
        pairs = sorted(_as_pairs(list(zip(scores, labels))), key=lambda pair: pair[0])
        if not pairs:
            raise CalibrationError("no training pairs")
        # PAV: maintain (weight, weighted_sum, x_high) blocks, merging violations.
        blocks: list[list[float]] = []
        for x, label in pairs:
            blocks.append([1.0, float(label), float(x)])
            while len(blocks) >= 2:
                left, right = blocks[-2], blocks[-1]
                if left[1] / left[0] <= right[1] / right[0]:
                    break
                merged = [left[0] + right[0], left[1] + right[1], right[2]]
                blocks.pop()
                blocks.pop()
                blocks.append(merged)
        self.blocks = tuple((high, total / weight) for weight, total, high in blocks)
        self.fitted = True
        return self

    def predict(self, score: float) -> float:
        if not self.fitted:
            raise CalibrationError("IsotonicRegression is not fitted")
        x = float(score)
        for high, value in self.blocks:
            if x <= high:
                return _clamp01(value)
        return _clamp01(self.blocks[-1][1])

    def to_dict(self) -> dict[str, Any]:
        return {"kind": "isotonic", "blocks": [list(block) for block in self.blocks], "fitted": self.fitted}

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "IsotonicRegression":
        blocks = tuple((float(high), float(value)) for high, value in payload.get("blocks", []))
        return cls(blocks=blocks, fitted=bool(payload.get("fitted", bool(blocks))))


class Calibrator:
    """A trained (or untrained) score -> probability map.

    ``trained`` is ``False`` until ``fit`` succeeds on at least
    ``MIN_LABELED_PAIRS`` pairs with both labels present. Callers must surface
    this so an edge is only reported as ``calibrated: true`` when a real fit
    backs it.
    """

    def __init__(self, method: str = DEFAULT_METHOD, *, min_pairs: int = MIN_LABELED_PAIRS) -> None:
        if method not in METHODS:
            raise CalibrationError(f"unknown method {method!r}; expected one of {METHODS}")
        self.method = method
        self.min_pairs = min_pairs
        self.model: PlattScaling | IsotonicRegression | None = None
        self.pairs_fitted = 0

    @property
    def trained(self) -> bool:
        return self.model is not None

    def fit(self, pairs: Iterable[Any], *, method: str | None = None) -> "Calibrator":
        method = method or self.method
        if method not in METHODS:
            raise CalibrationError(f"unknown method {method!r}; expected one of {METHODS}")
        cleaned = _as_pairs(pairs)
        labels = {label for _, label in cleaned}
        if len(cleaned) < self.min_pairs or labels != {0, 1}:
            # Not enough evidence: stay untrained rather than fit a meaningless map.
            self.model = None
            self.pairs_fitted = 0
            self.method = method
            return self
        scores, y = _split(cleaned)
        model = PlattScaling() if method == "platt" else IsotonicRegression()
        model.fit(scores, y)
        self.method = method
        self.model = model
        self.pairs_fitted = len(cleaned)
        return self

    def predict(self, score: float) -> float:
        if self.model is None:
            raise CalibrationError("calibrator is not trained")
        return self.model.predict(score)

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "min_pairs": self.min_pairs,
            "trained": self.trained,
            "pairs_fitted": self.pairs_fitted,
            "model": self.model.to_dict() if self.model is not None else None,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Calibrator":
        calibrator = cls(str(payload.get("method", DEFAULT_METHOD)),
                         min_pairs=int(payload.get("min_pairs", MIN_LABELED_PAIRS)))
        model_payload = payload.get("model")
        if model_payload:
            kind = model_payload.get("kind")
            calibrator.model = (
                PlattScaling.from_dict(model_payload) if kind == "platt"
                else IsotonicRegression.from_dict(model_payload)
            )
            calibrator.pairs_fitted = int(payload.get("pairs_fitted", 0))
        return calibrator


def load_pairs(path: str | Path) -> list[dict[str, Any]]:
    """Load labelled pairs from the JSON fixture format (``{"pairs": [...]}``)."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        pairs = payload.get("pairs", [])
    else:
        pairs = payload
    return list(pairs)


def calibrator_from_file(path: str | Path, *, method: str | None = DEFAULT_METHOD,
                         min_pairs: int = MIN_LABELED_PAIRS) -> Calibrator:
    """Build a ``Calibrator`` from a labelled-pairs fixture.

    When ``method`` is ``None`` the fixture's own ``method`` field is honoured.
    """
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    fixture_method = payload.get("method") if isinstance(payload, dict) else None
    pairs = load_pairs(path)
    return Calibrator(method=method or fixture_method or DEFAULT_METHOD,
                      min_pairs=min_pairs).fit(pairs, method=method or fixture_method or DEFAULT_METHOD)
