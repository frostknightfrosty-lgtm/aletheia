"""Phase 18.3 semantic profile linking.

The model is deliberately absent from module import. ``sentence-transformers``
and its transitive Torch stack are expensive to import, so the first profile
pair with usable bio text imports and loads ``all-MiniLM-L6-v2``. A failed load
is reported to the caller, never allowed to break entity resolution.

``all-MiniLM-L6-v2`` is an English sentence model. To avoid confidently
comparing profiles written in scripts the model was not trained on, text whose
letters are predominantly non-Latin is skipped rather than embedded.
"""

from __future__ import annotations

import math
import threading
import unicodedata
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any

__all__ = [
    "BIO_ATTRIBUTE_KEYS",
    "TEXT_EMBEDDING_CONFIDENCE",
    "TEXT_EMBEDDING_MIN_CHARS",
    "TEXT_EMBEDDING_MODEL",
    "TEXT_EMBEDDING_THRESHOLD",
    "TextEmbedder",
    "cosine_similarity",
    "embed_texts",
    "profile_bio",
    "reset_text_embedding_model",
    "usable_bio",
]

TEXT_EMBEDDING_MODEL = "all-MiniLM-L6-v2"
TEXT_EMBEDDING_THRESHOLD = 0.85
TEXT_EMBEDDING_CONFIDENCE = 0.85
TEXT_EMBEDDING_MIN_CHARS = 10

# Adapter spellings for the free-text profile description. ``description`` is
# included because GitHub-style adapters use it for the profile bio; callers
# restrict comparison to profile-shaped entities so repository descriptions do
# not become identity evidence accidentally.
BIO_ATTRIBUTE_KEYS = (
    "bio",
    "biography",
    "description",
    "about",
    "summary",
    "headline",
    "tagline",
)

TextEmbedder = Callable[[Sequence[str]], Sequence[Sequence[float]]]

_model: Any | None = None
_model_error: str | None = None
_model_lock = threading.Lock()


def reset_text_embedding_model() -> None:
    """Drop the cached model (tests and long-lived processes after a failure)."""
    global _model, _model_error
    with _model_lock:
        _model = None
        _model_error = None


def _load_text_embedding_model() -> Any:
    """Import and load the sentence model once, on first semantic comparison."""
    global _model, _model_error
    if _model is not None:
        return _model
    with _model_lock:
        if _model is not None:
            return _model
        if _model_error is not None:
            raise RuntimeError(_model_error)
        try:
            from sentence_transformers import SentenceTransformer

            _model = SentenceTransformer(TEXT_EMBEDDING_MODEL)
        except Exception as exc:  # noqa: BLE001 - optional local model
            _model_error = (
                "semantic profile linking unavailable: could not load "
                f"{TEXT_EMBEDDING_MODEL}: {exc}"
            )
            raise RuntimeError(_model_error) from exc
    return _model


def embed_texts(
    texts: Sequence[str], embedder: TextEmbedder | None = None
) -> list[list[float]]:
    """Embed texts with the injected provider or the lazy default model."""
    normalized = [str(text).strip() for text in texts]
    if not normalized:
        return []
    if embedder is None:
        model = _load_text_embedding_model()
        raw_vectors = model.encode(
            normalized,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
    else:
        raw_vectors = embedder(normalized)
    output: list[list[float]] = []
    for vector in raw_vectors:
        values = [float(value) for value in vector]
        output.append(values)
    return output


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    """Cosine similarity for two real vectors; zero vectors are not similar."""
    if len(left) != len(right) or not left:
        raise ValueError("embedding vectors must have the same non-zero dimension")
    numerator = sum(float(a) * float(b) for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(float(value) ** 2 for value in left))
    right_norm = math.sqrt(sum(float(value) ** 2 for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    value = numerator / (left_norm * right_norm)
    return round(max(-1.0, min(1.0, value)), 6)


def _clean_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = " ".join(value.split())
    return cleaned or None


def profile_bio(attributes: Mapping[str, Any] | None) -> str | None:
    """Return the first non-empty profile bio field, case-insensitively."""
    if not attributes:
        return None
    lowered = {str(key).casefold(): value for key, value in attributes.items()}
    for key in BIO_ATTRIBUTE_KEYS:
        text = _clean_text(lowered.get(key))
        if text is not None:
            return text
    return None


def _is_latin_letter(character: str) -> bool:
    name = unicodedata.name(character, "")
    return name.startswith("LATIN")


def usable_bio(text: str | None, *, min_chars: int = TEXT_EMBEDDING_MIN_CHARS) -> bool:
    """Whether text is safe to compare with the English sentence model.

    Empty, numeric-only, very short, and predominantly non-Latin profiles are
    skipped. Multilingual Latin-script text (accented names, borrowed words)
    remains eligible; the model can still place it in its English vector space.
    """
    cleaned = _clean_text(text)
    if cleaned is None or len(cleaned) < min_chars:
        return False
    letters = [character for character in cleaned if character.isalpha()]
    if not letters:
        return False
    non_latin = sum(1 for character in letters if not _is_latin_letter(character))
    return non_latin / len(letters) <= 0.50


def unique_usable_bios(texts: Iterable[str | None]) -> list[str]:
    """Deduplicate usable bios while preserving deterministic order."""
    seen: set[str] = set()
    output: list[str] = []
    for text in texts:
        cleaned = _clean_text(text)
        if cleaned is None or cleaned in seen or not usable_bio(cleaned):
            continue
        seen.add(cleaned)
        output.append(cleaned)
    return output
