"""Storage conformance against real services (CI only).

Each backend runs the full shared contract (``aletheia.storage.conformance``).
A backend is skipped *only* when its connection environment variable is unset —
which is the case on developer machines without Docker. In CI every variable is
set, so a backend that fails to connect or fails a check fails the suite rather
than being skipped.
"""

from __future__ import annotations

import json
import os

import pytest

from aletheia.storage import ENV_VARS, NETWORKED_BACKENDS, open_backend
from aletheia.storage.conformance import conform


def _env_var(name: str) -> str:
    return ENV_VARS[name]


@pytest.mark.integration
@pytest.mark.parametrize("name", NETWORKED_BACKENDS)
def test_backend_conforms(name: str) -> None:
    value = os.environ.get(_env_var(name))
    if not value:
        pytest.skip(f"{_env_var(name)} is not set (no storage service configured)")

    backend = open_backend(name, value)
    try:
        health = backend.health()
        assert health["ok"] is True, f"{name} is unreachable: {health}"

        result = conform(backend)

        if name == "elasticsearch":
            # Proven only against a real engine: the search capability the other
            # backends do not have. The conformance run left a stored graph.
            run_id = result["run_id"]
            backend.save_graph(run_id, {"entities": [{"canonical_value": "example.com"}], "edges": []})
            found = backend.search_entities(run_id, "example.com")
            assert [entity["canonical_value"] for entity in found] == ["example.com"]
    finally:
        backend.close()

    assert result["ok"] is True, f"{name} failed conformance:\n{json.dumps(result, indent=2)}"
