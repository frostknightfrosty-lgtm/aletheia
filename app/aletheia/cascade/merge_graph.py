"""Confirmed-merge equality graph with union-find and conflict propagation.

Design of record: ``docs/PIVOT_CASCADE.md`` section 6.3 — confirmed merges
form an equality graph (transitive); a later veto that contradicts a
confirmed chain re-opens the chain, demotes its weakest link, and records the
contradiction. No silent split, no silent merge.

Semantics:

- Only confirmed merges enter the graph. :meth:`MergeGraph.attempt_merge`
  accepts a ``ClusterDecision`` and merges only when the decision was
  accepted, carries ``IdentityTier.CONFIRMED``, and has a score; anything
  else is refused with a reason. There are no partial merges.
- :meth:`MergeGraph.conflict` records a contradiction. When the two endpoints
  are already in the same component, the shortest link path between them is
  found, the weakest link (lowest score; ties broken lexicographically) is
  demoted, and components are rebuilt from the surviving links — a chain
  conflict re-opens the chain and any resulting split is recorded on the
  conflict record. Conflicts across components are recorded without touching
  the graph.

Honest limits: weakest-link demotion is path-local (a full minimum-bottleneck
analysis across every alternative path is out of scope for v1), and link
scores must be finite numbers.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from uuid import UUID

from aletheia.core.models import ClusterDecision, IdentityTier

__all__ = ["ConflictRecord", "MergeGraph", "MergeLink"]


@dataclass(frozen=True)
class MergeLink:
    """One confirmed merge edge (the equality-graph unit)."""

    left: str
    right: str
    score: float
    reason: str = ""
    decision_id: UUID | None = None


@dataclass(frozen=True)
class ConflictRecord:
    """A recorded contradiction between two entity ids."""

    left: str
    right: str
    reason: str
    chain_reopened: bool
    demoted: MergeLink | None


class MergeGraph:
    """Union-find over confirmed merges, with recorded conflict propagation."""

    def __init__(self) -> None:
        self._links: dict[frozenset[str], MergeLink] = {}
        self._conflicts: list[ConflictRecord] = []
        self._demoted: list[MergeLink] = []
        self._known: set[str] = set()
        self._parent: dict[str, str] = {}
        self._rank: dict[str, int] = {}

    # -- union-find internals -------------------------------------------------

    def _rebuild(self) -> None:
        self._parent = {node: node for node in self._known}
        self._rank = {}
        for link in self._links.values():
            self._union(link.left, link.right)

    def find(self, node: str) -> str:
        parent = self._parent.setdefault(node, node)
        while parent != self._parent[parent]:
            self._parent[parent] = self._parent[self._parent[parent]]
            parent = self._parent[parent]
        self._parent[node] = parent
        return parent

    def _union(self, left: str, right: str) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root == right_root:
            return
        left_rank = self._rank.get(left_root, 0)
        right_rank = self._rank.get(right_root, 0)
        if left_rank < right_rank:
            left_root, right_root = right_root, left_root
        self._parent[right_root] = left_root
        if left_rank == right_rank:
            self._rank[left_root] = left_rank + 1

    # -- merge surface --------------------------------------------------------

    def merge(
        self,
        left: str,
        right: str,
        *,
        score: float,
        reason: str = "",
        decision_id: UUID | None = None,
    ) -> MergeLink:
        """Add one confirmed merge edge (the caller asserts confirmedness)."""
        if left == right:
            raise ValueError("cannot merge an entity with itself")
        if not math.isfinite(score):
            raise ValueError("merge score must be finite")
        key = frozenset({left, right})
        if key in self._links:
            raise ValueError(f"pair already merged: {left!r} <-> {right!r}")
        link = MergeLink(
            left=left, right=right, score=float(score), reason=reason, decision_id=decision_id
        )
        self._links[key] = link
        self._known.update((left, right))
        self._union(left, right)
        return link

    def attempt_merge(self, decision: ClusterDecision) -> tuple[bool, str]:
        """Merge a decision's entities when it is an accepted confirmed merge.

        Returns ``(merged, reason)``; a refused decision changes nothing.
        Re-attempts are idempotent (already-present pairs are skipped).
        """
        if not decision.accepted:
            return False, "decision was not accepted"
        if decision.tier is not IdentityTier.CONFIRMED:
            return False, f"tier {decision.tier} cannot merge (confirmed only)"
        if decision.score is None:
            return False, "confirmed merge without a score"
        ids = [str(entity_id) for entity_id in decision.entity_ids]
        if len(set(ids)) != len(ids):
            return False, "decision repeats an entity"
        merged_any = False
        for other in ids[1:]:
            if frozenset({ids[0], other}) in self._links:
                continue
            self.merge(
                ids[0],
                other,
                score=decision.score,
                reason=decision.reason,
                decision_id=decision.decision_id,
            )
            merged_any = True
        if not merged_any:
            return False, "all pairs already merged"
        return True, ""

    # -- conflicts ------------------------------------------------------------

    def conflict(self, left: str, right: str, *, reason: str) -> ConflictRecord:
        """Record a contradiction, re-opening same-component chains."""
        self._known.update((left, right))
        chain_reopened = self.find(left) == self.find(right)
        demoted: MergeLink | None = None
        if chain_reopened:
            path = self._shortest_path_links(left, right)
            weakest = min(
                path,
                key=lambda link: (
                    link.score,
                    min(link.left, link.right),
                    max(link.left, link.right),
                ),
            )
            del self._links[frozenset({weakest.left, weakest.right})]
            self._demoted.append(weakest)
            self._rebuild()
            demoted = weakest
        record = ConflictRecord(
            left=left,
            right=right,
            reason=reason,
            chain_reopened=chain_reopened,
            demoted=demoted,
        )
        self._conflicts.append(record)
        return record

    def _shortest_path_links(self, left: str, right: str) -> list[MergeLink]:
        adjacency: dict[str, list[MergeLink]] = {}
        for link in self._links.values():
            adjacency.setdefault(link.left, []).append(link)
            adjacency.setdefault(link.right, []).append(link)
        came_from: dict[str, MergeLink] = {}
        seen = {left}
        queue: deque[str] = deque([left])
        while queue:
            node = queue.popleft()
            if node == right:
                break
            for link in adjacency.get(node, ()):
                neighbour = link.right if link.left == node else link.left
                if neighbour not in seen:
                    seen.add(neighbour)
                    came_from[neighbour] = link
                    queue.append(neighbour)
        if right not in seen:
            raise RuntimeError(
                "conflict endpoints share a component but no link path exists"
            )
        path: list[MergeLink] = []
        node = right
        while node != left:
            link = came_from[node]
            path.append(link)
            node = link.left if link.right == node else link.right
        return path

    # -- inspection -----------------------------------------------------------

    def component(self, node: str) -> frozenset[str]:
        root = self.find(node)
        return frozenset(
            {node} | {candidate for candidate in self._parent if self.find(candidate) == root}
        )

    def groups(self) -> list[frozenset[str]]:
        """All components, deterministically ordered."""
        roots: dict[str, set[str]] = {}
        for node in self._parent:
            roots.setdefault(self.find(node), set()).add(node)
        return sorted(
            (frozenset(members) for members in roots.values()),
            key=lambda members: sorted(members),
        )

    def nodes(self) -> frozenset[str]:
        return frozenset(self._known)

    def links(self) -> tuple[MergeLink, ...]:
        return tuple(
            self._links[key] for key in sorted(self._links, key=lambda key: sorted(key))
        )

    def conflicts(self) -> tuple[ConflictRecord, ...]:
        return tuple(self._conflicts)

    def demoted_links(self) -> tuple[MergeLink, ...]:
        return tuple(self._demoted)
