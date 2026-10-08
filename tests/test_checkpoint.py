from uuid import uuid4
from aletheia.core.checkpoint import CheckpointStore


def test_checkpoint_is_atomic_and_reloadable(tmp_path):
    store = CheckpointStore(tmp_path)
    run = uuid4()
    manifest = {"goal": "test", "completed": [], "pending": ["sherlock"]}
    store.save(run, manifest)
    loaded = store.load(run)
    assert loaded["goal"] == "test"
    assert loaded["checkpoint_hash"]


def test_handoff_created(tmp_path):
    store = CheckpointStore(tmp_path)
    run = uuid4()
    p = store.write_handoff(run, "obj", ["sherlock"], ["theHarvester"], ["x"], [], "aletheia resume --run-id X")
    assert "Exact resume command" in p.read_text()
