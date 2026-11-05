"""Historial local en SQLite: ofertas vistas, scores cacheados y estado (aplicada/descartada)."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

from .models import Job, Match

STATUSES = ("new", "saved", "applied", "discarded")

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    data TEXT NOT NULL,
    first_seen TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'new'
);
CREATE TABLE IF NOT EXISTS scores (
    job_id TEXT NOT NULL,
    cache_key TEXT NOT NULL,
    data TEXT NOT NULL,
    scored_at TEXT NOT NULL,
    PRIMARY KEY (job_id, cache_key)
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: Path):
        path = Path(path)
        if str(path) != ":memory:":
            path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path))
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        self.conn.close()

    # --- ofertas ---------------------------------------------------------
    def upsert_jobs(self, jobs: Iterable[Job]) -> Set[str]:
        """Guarda las ofertas; devuelve los ids vistos por primera vez."""
        new_ids: Set[str] = set()
        for job in jobs:
            row = self.conn.execute("SELECT 1 FROM jobs WHERE id = ?", (job.id,)).fetchone()
            payload = json.dumps(job.to_dict(), ensure_ascii=False)
            if row is None:
                self.conn.execute(
                    "INSERT INTO jobs (id, data, first_seen) VALUES (?, ?, ?)",
                    (job.id, payload, _now()),
                )
                new_ids.add(job.id)
            else:
                self.conn.execute("UPDATE jobs SET data = ? WHERE id = ?", (payload, job.id))
        self.conn.commit()
        return new_ids

    def statuses(self, job_ids: Iterable[str]) -> Dict[str, str]:
        ids = list(job_ids)
        out: Dict[str, str] = {}
        for i in range(0, len(ids), 500):
            chunk = ids[i : i + 500]
            marks = ",".join("?" * len(chunk))
            for jid, status in self.conn.execute(
                "SELECT id, status FROM jobs WHERE id IN (%s)" % marks, chunk
            ):
                out[jid] = status
        return out

    def set_status(self, job_id: str, status: str) -> bool:
        if status not in STATUSES:
            raise ValueError("Estado inválido: %s (válidos: %s)" % (status, ", ".join(STATUSES)))
        cur = self.conn.execute("UPDATE jobs SET status = ? WHERE id = ?", (status, job_id))
        self.conn.commit()
        return cur.rowcount > 0

    def list_jobs(
        self, status: Optional[str] = None, limit: int = 50, cache_key: Optional[str] = None
    ) -> List[Tuple[Job, str, Optional[Match]]]:
        """Ofertas guardadas (más recientes primero) con su estado y score cacheado si existe."""
        query = "SELECT id, data, status FROM jobs"
        params: list = []
        if status:
            query += " WHERE status = ?"
            params.append(status)
        query += " ORDER BY first_seen DESC LIMIT ?"
        params.append(limit)
        rows = self.conn.execute(query, params).fetchall()
        scores = self.get_scores([r[0] for r in rows], cache_key) if cache_key else {}
        return [(Job.from_dict(json.loads(r[1])), r[2], scores.get(r[0])) for r in rows]

    # --- scores ----------------------------------------------------------
    def get_scores(self, job_ids: Iterable[str], cache_key: str) -> Dict[str, Match]:
        ids = list(job_ids)
        out: Dict[str, Match] = {}
        for i in range(0, len(ids), 500):
            chunk = ids[i : i + 500]
            marks = ",".join("?" * len(chunk))
            for jid, data in self.conn.execute(
                "SELECT job_id, data FROM scores WHERE cache_key = ? AND job_id IN (%s)" % marks,
                [cache_key] + chunk,
            ):
                out[jid] = Match.from_dict(json.loads(data))
        return out

    def save_scores(self, matches: Iterable[Match], cache_key: str) -> None:
        for m in matches:
            self.conn.execute(
                "INSERT OR REPLACE INTO scores (job_id, cache_key, data, scored_at) VALUES (?, ?, ?, ?)",
                (m.job_id, cache_key, json.dumps(m.to_dict(), ensure_ascii=False), _now()),
            )
        self.conn.commit()
