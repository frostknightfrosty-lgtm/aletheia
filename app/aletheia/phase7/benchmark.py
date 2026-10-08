from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from uuid import uuid4


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class BenchmarkCase:
    case_id: str
    adapter: str
    seed_type: str
    seed_value: str
    expected: frozenset[str]
    observed: frozenset[str]
    duration_ms: float
    negative_count: int | None = None
    cost: float | None = None


class BenchmarkStore:
    """SQLite-backed labeled benchmark store. Metrics are computed only from submitted labels."""
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as con:
            con.execute("""
                CREATE TABLE IF NOT EXISTS benchmark_cases (
                    case_id TEXT PRIMARY KEY,
                    adapter TEXT NOT NULL,
                    seed_type TEXT NOT NULL,
                    seed_value TEXT NOT NULL,
                    expected_json TEXT NOT NULL,
                    observed_json TEXT NOT NULL,
                    duration_ms REAL NOT NULL,
                    negative_count INTEGER,
                    cost REAL,
                    created_at TEXT NOT NULL
                )
            """)
            con.execute("""
                CREATE TABLE IF NOT EXISTS execution_samples (
                    sample_id TEXT PRIMARY KEY,
                    adapter TEXT NOT NULL,
                    duration_ms REAL NOT NULL,
                    cost REAL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        return con

    def record(self, *, adapter: str, seed_type: str, seed_value: str,
               expected: Iterable[str], observed: Iterable[str], duration_ms: float,
               negative_count: int | None = None, cost: float | None = None,
               case_id: str | None = None) -> str:
        cid = case_id or str(uuid4())
        exp = sorted(set(expected)); obs = sorted(set(observed))
        with self._connect() as con:
            con.execute(
                "INSERT INTO benchmark_cases(case_id,adapter,seed_type,seed_value,expected_json,observed_json,duration_ms,negative_count,cost,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (cid, adapter, seed_type, seed_value, json.dumps(exp), json.dumps(obs), float(duration_ms), negative_count, cost, _now()),
            )
        return cid

    def record_execution(self, *, adapter: str, duration_ms: float, status: str, cost: float | None = None, sample_id: str | None = None) -> str:
        sid = sample_id or str(uuid4())
        with self._connect() as con:
            con.execute("INSERT INTO execution_samples(sample_id,adapter,duration_ms,cost,status,created_at) VALUES(?,?,?,?,?,?)",
                        (sid, adapter, float(duration_ms), cost, status, _now()))
        return sid

    def metrics(self) -> list[dict]:
        with self._connect() as con:
            rows = con.execute("SELECT * FROM benchmark_cases ORDER BY adapter, created_at").fetchall()
            exec_rows = con.execute("SELECT * FROM execution_samples ORDER BY adapter, created_at").fetchall()
        grouped: dict[str, dict] = {}
        for row in rows:
            bucket = grouped.setdefault(row["adapter"], {
                "adapter": row["adapter"], "cases": 0, "expected_total": 0, "observed_total": 0,
                "true_positive": 0, "false_positive": 0, "false_negative": 0,
                "negative_total": 0, "duration_ms_total": 0.0, "cost_total": 0.0, "cost_samples": 0,
            })
            exp = set(json.loads(row["expected_json"])); obs = set(json.loads(row["observed_json"]))
            tp = len(exp & obs); fp = len(obs - exp); fn = len(exp - obs)
            bucket["cases"] += 1; bucket["expected_total"] += len(exp); bucket["observed_total"] += len(obs)
            bucket["true_positive"] += tp; bucket["false_positive"] += fp; bucket["false_negative"] += fn
            bucket["duration_ms_total"] += row["duration_ms"]
            if row["negative_count"] is not None: bucket["negative_total"] += int(row["negative_count"])
            if row["cost"] is not None:
                bucket["cost_total"] += float(row["cost"]); bucket["cost_samples"] += 1
        execution: dict[str, list[sqlite3.Row]] = {}
        for row in exec_rows:
            execution.setdefault(row["adapter"], []).append(row)
        for adapter, samples in execution.items():
            b=grouped.setdefault(adapter, {
                "adapter":adapter,"cases":0,"expected_total":0,"observed_total":0,
                "true_positive":0,"false_positive":0,"false_negative":0,"negative_total":0,
                "duration_ms_total":0.0,"cost_total":0.0,"cost_samples":0,
            })
            b["execution_duration_ms_total"] = 0.0
            b["execution_cost_total"] = 0.0
            b["execution_cost_samples"] = 0
            for sample in samples:
                b["execution_duration_ms_total"] += float(sample["duration_ms"])
                if sample["cost"] is not None:
                    b["execution_cost_total"] += float(sample["cost"]); b["execution_cost_samples"] += 1
            b["execution_samples"] = len(samples)
        out=[]
        for b in grouped.values():
            tp, fp, fn = b["true_positive"], b["false_positive"], b["false_negative"]
            predicted = tp + fp; actual = tp + fn
            b["precision"] = tp / predicted if predicted else None
            b["recall"] = tp / actual if actual else None
            b["coverage"] = tp / b["expected_total"] if b["expected_total"] else None
            negatives = b["negative_total"]
            b["false_positive_rate"] = fp / (fp + negatives) if (fp + negatives) else None
            b["avg_duration_ms"] = (
                b["execution_duration_ms_total"] / b["execution_samples"]
                if b.get("execution_samples") else (b["duration_ms_total"] / b["cases"] if b["cases"] else None)
            )
            b["avg_cost"] = (
                b["execution_cost_total"] / b["execution_cost_samples"]
                if b.get("execution_cost_samples") else (b["cost_total"] / b["cost_samples"] if b["cost_samples"] else None)
            )
            b["label_quality"] = "labeled" if b["expected_total"] or b["negative_total"] else "unlabeled"
            b["execution_samples"] = b.get("execution_samples", 0)
            out.append({k:v for k,v in b.items() if not k.endswith("_total") and k not in {"expected_total","observed_total","duration_ms_total","cost_total","negative_total","execution_duration_ms_total","execution_cost_total","execution_cost_samples"}})
        out.sort(key=lambda x: (x["recall"] is None, -(x["recall"] or 0.0), -(x["precision"] or 0.0), x["avg_duration_ms"] or float("inf")))
        for i,row in enumerate(out, 1): row["rank"] = i
        return out

    def leaderboard(self) -> list[dict]:
        return self.metrics()
