"""Historial local en SQLite: ofertas vistas y su estado (nueva/guardada/aplicada/descartada)."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

from .models import Job

STATUSES = ("new", "saved", "applied", "discarded")

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    data TEXT NOT NULL,
    first_seen TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'new'
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

    def list_jobs(self, status: Optional[str] = None, limit: int = 50) -> List[Tuple[Job, str]]:
        """Ofertas guardadas (más recientes primero) con su estado."""
        query = "SELECT data, status FROM jobs"
        params: list = []
        if status:
            query += " WHERE status = ?"
            params.append(status)
        query += " ORDER BY first_seen DESC LIMIT ?"
        params.append(limit)
        return [(Job.from_dict(json.loads(data)), st) for data, st in self.conn.execute(query, params)]
