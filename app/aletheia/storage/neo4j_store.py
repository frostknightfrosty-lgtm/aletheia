"""Neo4j storage backend (graph snapshots + native entity/edge materialisation).

Unlike the document-only backends this one does two things:

* stores the canonical JSON snapshot so a graph round-trips byte-for-byte, and
* materialises entities as ``(:Entity)`` nodes and edges as ``[:RELATED]``
  relationships scoped by ``run_id``, so the graph can be traversed in Cypher.

``verify_materialised`` is the conformance hook that asserts the native
representation really exists, which is what makes this a graph-database backend
rather than a blob store with a Cypher front end.

Configuration::

    ALETHEIA_STORAGE_NEO4J=neo4j://neo4j:password@localhost:7687
"""

from __future__ import annotations

import json
from typing import Any

from aletheia.storage.base import Migration, StorageBackend
from aletheia.storage.dsn import parse_dsn

_MIGRATIONS = [
    Migration(
        version=1,
        name="uniqueness_constraints",
        statement=(
            "CREATE CONSTRAINT aletheia_graph_run_id IF NOT EXISTS FOR (g:AletheiaGraph) REQUIRE g.run_id IS UNIQUE",
            "CREATE CONSTRAINT aletheia_manifest_run_id IF NOT EXISTS FOR (m:AletheiaManifest) REQUIRE m.run_id IS UNIQUE",
            "CREATE CONSTRAINT aletheia_migration_version IF NOT EXISTS FOR (s:AletheiaMigration) REQUIRE s.version IS UNIQUE",
            "CREATE CONSTRAINT aletheia_entity_key IF NOT EXISTS FOR (e:AletheiaEntity) REQUIRE (e.run_id, e.entity_id) IS UNIQUE",
        ),
    )
]


class Neo4jBackend(StorageBackend):
    backend_name = "neo4j"

    def __init__(self, url: str, *, driver: Any | None = None) -> None:
        self._url = url
        self._dsn = parse_dsn(url, default_port=7687)
        self._driver = driver

    @classmethod
    def from_env(cls, value: str) -> "Neo4jBackend":
        return cls(value)

    def _graph(self):
        if self._driver is None:
            import neo4j

            auth = (self._dsn.username or "neo4j", self._dsn.password or "")
            self._driver = neo4j.GraphDatabase.driver(
                f"{self._dsn.scheme}://{self._dsn.host}:{self._dsn.port}", auth=auth
            )
        return self._driver

    def _run(self, query: str, **params: Any) -> list[dict[str, Any]]:
        with self._graph().session() as session:
            result = session.run(query, **params)
            return [record.data() for record in result]

    # -- graph snapshots -------------------------------------------------
    def save_graph(self, run_id: str, graph: dict[str, Any]) -> str:
        self._run(
            "MERGE (g:AletheiaGraph {run_id: $run_id}) SET g.payload = $payload",
            run_id=run_id,
            payload=json.dumps(graph),
        )
        self._materialise(run_id, graph)
        return f"neo4j:(:AletheiaGraph {{run_id: {run_id}}})"

    def _materialise(self, run_id: str, graph: dict[str, Any]) -> None:
        self._run("MATCH (e:AletheiaEntity {run_id: $run_id}) DETACH DELETE e", run_id=run_id)
        entities = graph.get("entities", []) or []
        edges = graph.get("edges", []) or []
        if entities:
            self._run(
                "UNWIND $entities AS e"
                " MERGE (n:AletheiaEntity {run_id: $run_id, entity_id: e.entity_id})"
                " SET n.entity_type = e.entity_type, n.canonical_value = e.canonical_value,"
                "     n.attributes = e.attributes_json",
                run_id=run_id,
                entities=[
                    {
                        "entity_id": entity["entity_id"],
                        "entity_type": entity.get("entity_type"),
                        "canonical_value": entity.get("canonical_value"),
                        "attributes_json": json.dumps(entity.get("attributes", {})),
                    }
                    for entity in entities
                ],
            )
        if edges:
            self._run(
                "UNWIND $edges AS x"
                " MATCH (a:AletheiaEntity {run_id: $run_id, entity_id: x.source_entity_id})"
                " MATCH (b:AletheiaEntity {run_id: $run_id, entity_id: x.target_entity_id})"
                " MERGE (a)-[r:RELATED {run_id: $run_id, edge_id: x.edge_id}]->(b)"
                " SET r.relationship = x.relationship, r.confidence = x.confidence,"
                "     r.attributes = x.attributes_json",
                run_id=run_id,
                edges=[
                    {
                        "edge_id": edge["edge_id"],
                        "source_entity_id": edge.get("source_entity_id"),
                        "target_entity_id": edge.get("target_entity_id"),
                        "relationship": edge.get("relationship"),
                        "confidence": edge.get("confidence"),
                        "attributes_json": json.dumps(edge.get("attributes", {})),
                    }
                    for edge in edges
                ],
            )

    def load_graph(self, run_id: str) -> dict[str, Any] | None:
        rows = self._run("MATCH (g:AletheiaGraph {run_id: $run_id}) RETURN g.payload AS payload", run_id=run_id)
        if not rows:
            return None
        return json.loads(rows[0]["payload"])

    def verify_materialised(self, run_id: str, entities: int, edges: int) -> dict[str, int]:
        rows = self._run(
            "MATCH (n:AletheiaEntity {run_id: $run_id})"
            " OPTIONAL MATCH (:AletheiaEntity {run_id: $run_id})-[r:RELATED {run_id: $run_id}]->()"
            " RETURN count(DISTINCT n) AS entities, count(DISTINCT r) AS edges",
            run_id=run_id,
        )
        observed = {"entities": int(rows[0]["entities"]), "edges": int(rows[0]["edges"])}
        if observed != {"entities": entities, "edges": edges}:
            raise AssertionError(f"materialised graph mismatch: {observed} != entities={entities} edges={edges}")
        return observed

    # -- run manifests ---------------------------------------------------
    def save_manifest(self, run_id: str, manifest: dict[str, Any]) -> None:
        self._run(
            "MERGE (m:AletheiaManifest {run_id: $run_id}) SET m.payload = $payload",
            run_id=run_id,
            payload=json.dumps(manifest),
        )

    def load_manifest(self, run_id: str) -> dict[str, Any] | None:
        rows = self._run("MATCH (m:AletheiaManifest {run_id: $run_id}) RETURN m.payload AS payload", run_id=run_id)
        if not rows:
            return None
        return json.loads(rows[0]["payload"])

    # -- introspection ---------------------------------------------------
    def list_runs(self) -> list[str]:
        rows = self._run(
            "MATCH (n) WHERE n:AletheiaGraph OR n:AletheiaManifest"
            " RETURN DISTINCT n.run_id AS run_id ORDER BY run_id"
        )
        return [str(row["run_id"]) for row in rows]

    def health(self) -> dict[str, Any]:
        try:
            self._graph().verify_connectivity()
            return {"backend": self.backend_name, "ok": True, "host": self._dsn.host, "port": self._dsn.port}
        except Exception as exc:  # noqa: BLE001 - health never raises
            return {"backend": self.backend_name, "ok": False, "detail": f"{type(exc).__name__}: {exc}"}

    def close(self) -> None:
        if self._driver is not None:
            try:
                self._driver.close()
            finally:
                self._driver = None

    # -- migrations ------------------------------------------------------
    def migrations(self) -> list[Migration]:
        return list(_MIGRATIONS)

    def apply_migration(self, migration: Migration) -> None:
        for statement in migration.statement:
            self._run(statement)

    def applied_migrations(self) -> list[dict[str, Any]]:
        rows = self._run(
            "MATCH (s:AletheiaMigration) RETURN s.version AS version, s.name AS name,"
            " s.checksum AS checksum, s.applied_at AS applied_at ORDER BY version"
        )
        return [
            {
                "version": int(row["version"]),
                "name": row["name"],
                "checksum": row["checksum"],
                "applied_at": row["applied_at"],
            }
            for row in rows
        ]

    def record_migration(self, applied: dict[str, Any]) -> None:
        self._run(
            "MERGE (s:AletheiaMigration {version: $version})"
            " SET s.name = $name, s.checksum = $checksum, s.applied_at = $applied_at",
            version=applied["version"],
            name=applied["name"],
            checksum=applied["checksum"],
            applied_at=applied["applied_at"],
        )
