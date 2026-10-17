"""MinIO / S3 storage backend (run manifests and graph snapshots as objects).

Documents are stored as one JSON object per run in dedicated buckets. This is
the durable-blob backend: it is where large graph exports and future per-adapter
artefacts would live.

Configuration::

    ALETHEIA_STORAGE_MINIO=minio://access_key:secret_key@localhost:9000
"""

from __future__ import annotations

import io
import json
from typing import Any

from aletheia.storage.base import Migration, StorageBackend
from aletheia.storage.dsn import parse_dsn

_GRAPHS_BUCKET = "aletheia-graphs"
_MANIFESTS_BUCKET = "aletheia-manifests"
_META_BUCKET = "aletheia-meta"
_SCHEMA_PREFIX = "schema/"

_MIGRATIONS = [
    Migration(
        version=1,
        name="document_buckets",
        statement="create aletheia-graphs, aletheia-manifests and aletheia-meta buckets",
    )
]


class MinioBackend(StorageBackend):
    backend_name = "minio"

    def __init__(self, url: str, *, client: Any | None = None) -> None:
        self._url = url
        self._dsn = parse_dsn(url, default_port=9000)
        self._client = client

    @classmethod
    def from_env(cls, value: str) -> "MinioBackend":
        return cls(value)

    def _minio(self):
        if self._client is None:
            import minio

            secure = self._dsn.scheme in {"minios", "https"} or self._dsn.params.get("secure") == "true"
            self._client = minio.Minio(
                f"{self._dsn.host}:{self._dsn.port}",
                access_key=self._dsn.username,
                secret_key=self._dsn.password,
                secure=secure,
            )
        return self._client

    def _put_json(self, bucket: str, key: str, payload: dict[str, Any]) -> None:
        data = json.dumps(payload).encode("utf-8")
        self._minio().put_object(
            bucket, key, io.BytesIO(data), length=len(data), content_type="application/json"
        )

    def _get_json(self, bucket: str, key: str) -> dict[str, Any] | None:
        try:
            response = self._minio().get_object(bucket, key)
        except Exception as exc:  # noqa: BLE001 - NoSuchKey means absent
            if getattr(exc, "code", None) in {"NoSuchKey", "NoSuchBucket"}:
                return None
            raise
        try:
            return json.loads(response.read().decode("utf-8"))
        finally:
            response.close()
            response.release_conn()

    # -- graph snapshots -------------------------------------------------
    def save_graph(self, run_id: str, graph: dict[str, Any]) -> str:
        key = f"{run_id}.json"
        self._put_json(_GRAPHS_BUCKET, key, graph)
        return f"s3://{_GRAPHS_BUCKET}/{key}"

    def load_graph(self, run_id: str) -> dict[str, Any] | None:
        return self._get_json(_GRAPHS_BUCKET, f"{run_id}.json")

    # -- run manifests ---------------------------------------------------
    def save_manifest(self, run_id: str, manifest: dict[str, Any]) -> None:
        self._put_json(_MANIFESTS_BUCKET, f"{run_id}.json", manifest)

    def load_manifest(self, run_id: str) -> dict[str, Any] | None:
        return self._get_json(_MANIFESTS_BUCKET, f"{run_id}.json")

    # -- introspection ---------------------------------------------------
    def _objects(self, bucket: str) -> list[str]:
        try:
            return [obj.object_name for obj in self._minio().list_objects(bucket, recursive=True)]
        except Exception as exc:  # noqa: BLE001 - missing bucket means empty
            if getattr(exc, "code", None) in {"NoSuchBucket", "NoSuchKey"}:
                return []
            raise

    def list_runs(self) -> list[str]:
        runs = set()
        for bucket in (_GRAPHS_BUCKET, _MANIFESTS_BUCKET):
            for name in self._objects(bucket):
                if name.endswith(".json"):
                    runs.add(name[: -len(".json")])
        return sorted(runs)

    def health(self) -> dict[str, Any]:
        try:
            self._minio().list_buckets()
            return {"backend": self.backend_name, "ok": True, "host": self._dsn.host, "port": self._dsn.port}
        except Exception as exc:  # noqa: BLE001 - health never raises
            return {"backend": self.backend_name, "ok": False, "detail": f"{type(exc).__name__}: {exc}"}

    # -- migrations ------------------------------------------------------
    def migrations(self) -> list[Migration]:
        return list(_MIGRATIONS)

    def apply_migration(self, migration: Migration) -> None:
        if migration.version != 1:
            raise ValueError(f"unknown migration version {migration.version}")
        client = self._minio()
        for bucket in (_GRAPHS_BUCKET, _MANIFESTS_BUCKET, _META_BUCKET):
            if not client.bucket_exists(bucket):
                client.make_bucket(bucket)

    def applied_migrations(self) -> list[dict[str, Any]]:
        rows = []
        for name in self._objects(_META_BUCKET):
            if name.startswith(_SCHEMA_PREFIX) and name.endswith(".json"):
                payload = self._get_json(_META_BUCKET, name)
                if payload is not None:
                    rows.append(payload)
        return sorted(rows, key=lambda row: int(row["version"]))

    def record_migration(self, applied: dict[str, Any]) -> None:
        self._put_json(_META_BUCKET, f"{_SCHEMA_PREFIX}{int(applied['version']):04d}.json", applied)
