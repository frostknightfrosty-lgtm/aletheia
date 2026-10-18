"""Next-actions checklist (P17.8).

Design of record: ``docs/PIVOT_CASCADE.md`` section 12 — "free keys to
register (and exactly what each unlocks), clusters to confirm, missing seed
types to supply, sources blocked that may open later".

``KEY_ACTIONS`` and ``PERMISSION_ACTIONS`` are data copied from
``docs/USER_ACTIONS.md`` (sections 1 and 2 — the campaign's single source of
truth for owner-gated items); keep them in sync when that document changes.
Blocked sources come from the blind-spot registry or the caller; nothing here
is guessed.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

__all__ = ["KEY_ACTIONS", "PERMISSION_ACTIONS", "build_next_actions"]

# Copied from docs/USER_ACTIONS.md section 1 (Gate 3 free keys, recorded).
KEY_ACTIONS: tuple[dict[str, str], ...] = (
    {
        "secret": "LEAKIX_API_KEY",
        "unlocks": "live leak_checkers path",
        "signup": "leakix.net",
    },
    {
        "secret": "GRAYHATWARFARE_TOKEN",
        "unlocks": "live leak_checkers path",
        "signup": "grayhatwarfare.com",
    },
    {
        "secret": "REDDIT_CLIENT_ID + REDDIT_CLIENT_SECRET",
        "unlocks": "reddit-api adapter",
        "signup": "reddit.com/prefs/apps",
    },
    {
        "secret": "YOUTUBE_API_KEY",
        "unlocks": "youtube-api adapter + youtube-geofind",
        "signup": "Google Cloud console",
    },
)

# Copied from docs/USER_ACTIONS.md section 2 (provider permissions).
PERMISSION_ACTIONS: tuple[dict[str, str], ...] = (
    {
        "provider": "OpenSky",
        "note": (
            "terms require written permission for REST integration; needed for "
            "transport_movement live coverage"
        ),
    },
    {
        "provider": "EUIPO",
        "note": "sandbox/production approval after the free developer account",
    },
)


def build_next_actions(
    *,
    clusters_to_confirm: Sequence[str] = (),
    missing_seed_types: Sequence[str] = (),
    blocked_sources: Mapping[str, str] | None = None,
    keys: Sequence[Mapping[str, str]] | None = None,
) -> dict[str, Any]:
    """Serialize the checklist, deterministically."""
    confirm = sorted({str(cluster) for cluster in clusters_to_confirm})
    missing = sorted({str(seed_type) for seed_type in missing_seed_types})
    blocked = {str(source): str(reason) for source, reason in (blocked_sources or {}).items()}
    return {
        "next_actions_version": 1,
        "free_keys": [dict(entry) for entry in (keys if keys is not None else KEY_ACTIONS)],
        "provider_permissions": [dict(entry) for entry in PERMISSION_ACTIONS],
        "confirm_clusters": confirm,
        "missing_seed_types": missing,
        "blocked_sources": [
            {"source": source, "reason": blocked[source]} for source in sorted(blocked)
        ],
    }
