"""Orchestrator failure policy: fail-stop by default, opt-in continue-on-error.

Readiness audit 2026-10-25: an unauthenticated ``instaloader`` run hung until its
timeout and, because the orchestrator is fail-stop, the 8 adapters queued behind it
never ran. Fail-stop stays the default (checkpoint, handoff, re-raise). The opt-in
``continue_on_error`` records the failure exactly the same way but keeps going.
No Docker daemon or network is required.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from aletheia.core.adapters import Adapter
from aletheia.core.execution import DockerExecutionError
from aletheia.core.models import (
    AdapterDescriptor,
    AdapterRunResult,
    EntityType,
    Finding,
    Provenance,
    Seed,
    SeedType,
)
from aletheia.core.orchestrator import Orchestrator


def _descriptor(name: str) -> AdapterDescriptor:
    return AdapterDescriptor(
        name=name,
        license="project-internal",
        input_types=[SeedType.USERNAME],
        output_types=[EntityType.USERNAME],
        legal_notes=[],
        rate_limit="n/a",
        invocation="test",
        version_pin="v1",
        upstream="https://example.invalid",
        network_required=False,
        docker_image="aletheia/test:v1",
    )


class _Adapter(Adapter):
    def __init__(self, name: str, *, fail: bool = False) -> None:
        self.descriptor = _descriptor(name)
        self.fail = fail
        self.ran = 0

    def supports(self, seed_type):
        return seed_type == SeedType.USERNAME

    def build_command(self, request, workspace):
        return ["runner.py"]

    def parse(self, request, workspace, stdout, stderr, exit_code):
        raise AssertionError("not used")

    def run(self, request, workspace, audit):
        self.ran += 1
        if self.fail:
            raise DockerExecutionError("container timed out after 1s")
        workspace.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc)
        finding = Finding(
            entity_type=EntityType.USERNAME,
            value="frost-test",
            provenance=Provenance(tool=self.descriptor.name, confidence=0.9, adapter_version="v1"),
        )
        return AdapterRunResult(
            run_id=request.run_id, adapter=self.descriptor, status="ok",
            started_at=now, finished_at=now, findings=[finding],
        )


def _orchestrator(tmp_path):
    orch = Orchestrator(tmp_path)
    orch.adapters = {
        "first": _Adapter("first"),
        "hangs": _Adapter("hangs", fail=True),
        "last": _Adapter("last"),
    }
    run_id = orch.create_run(Seed(type=SeedType.USERNAME, value="example"))
    return orch, run_id


def test_default_is_fail_stop_and_later_adapters_do_not_run(tmp_path):
    orch, run_id = _orchestrator(tmp_path)
    with pytest.raises(DockerExecutionError):
        orch.resume(run_id, wire_egress=False)
    manifest = orch.checkpoints.load(run_id)
    assert manifest["completed"] == ["first"]
    assert manifest["failed"] == ["hangs"]
    assert manifest["pending"] == ["hangs", "last"]
    assert orch.adapters["last"].ran == 0


def test_continue_on_error_records_the_failure_and_runs_the_rest(tmp_path):
    orch, run_id = _orchestrator(tmp_path)
    manifest = orch.resume(run_id, wire_egress=False, continue_on_error=True)
    assert manifest["completed"] == ["first", "last"]
    assert manifest["failed"] == ["hangs"]
    assert manifest["pending"] == ["hangs"]
    assert manifest["retry_counters"] == {"hangs": 1}
    assert orch.adapters["last"].ran == 1
    saved = orch.checkpoints.load(run_id)
    assert saved["failed"] == ["hangs"]
    assert saved["completed"] == ["first", "last"]
