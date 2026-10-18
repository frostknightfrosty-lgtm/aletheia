"""Tests for the next-actions checklist (P17.8)."""

from __future__ import annotations

from aletheia.cascade.next_actions import KEY_ACTIONS, PERMISSION_ACTIONS, build_next_actions


def test_default_checklist_copies_user_actions():
    checklist = build_next_actions()
    assert [entry["secret"] for entry in checklist["free_keys"]] == [
        entry["secret"] for entry in KEY_ACTIONS
    ]
    assert [entry["secret"] for entry in checklist["free_keys"]] == [
        "LEAKIX_API_KEY",
        "GRAYHATWARFARE_TOKEN",
        "REDDIT_CLIENT_ID + REDDIT_CLIENT_SECRET",
        "YOUTUBE_API_KEY",
    ]
    assert [entry["provider"] for entry in checklist["provider_permissions"]] == [
        entry["provider"] for entry in PERMISSION_ACTIONS
    ]
    assert checklist["confirm_clusters"] == []
    assert checklist["missing_seed_types"] == []
    assert checklist["blocked_sources"] == []


def test_checklist_sorts_and_dedups():
    checklist = build_next_actions(
        clusters_to_confirm=["b", "a", "a"],
        missing_seed_types=["phone", "email", "phone"],
        blocked_sources={"z": "reason z", "a": "reason a"},
    )
    assert checklist["confirm_clusters"] == ["a", "b"]
    assert checklist["missing_seed_types"] == ["email", "phone"]
    assert [entry["source"] for entry in checklist["blocked_sources"]] == ["a", "z"]
    assert checklist["blocked_sources"][0] == {"source": "a", "reason": "reason a"}


def test_custom_keys_override():
    checklist = build_next_actions(keys=[{"secret": "X", "unlocks": "y", "signup": "z"}])
    assert checklist["free_keys"] == [{"secret": "X", "unlocks": "y", "signup": "z"}]
