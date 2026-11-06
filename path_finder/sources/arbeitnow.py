"""Arbeitnow — API pública sin clave. Foco en Europa (sobre todo Alemania); trae flag `remote`."""
from __future__ import annotations

import time
from typing import List

from ..models import Job, Preferences, html_to_text
from .base import Source, iso_from_epoch

PAGES = 3


class Arbeitnow(Source):
    name = "arbeitnow"
    label = "Arbeitnow"
    homepage = "https://www.arbeitnow.com"
    URL = "https://www.arbeitnow.com/api/job-board-api"

    def fetch(self, prefs: Preferences, client) -> List[Job]:
        jobs: List[Job] = []
        for page in range(1, PAGES + 1):
            resp = client.get(self.URL, params={"page": page})
            resp.raise_for_status()
            data = resp.json().get("data", [])
            jobs.extend(self._parse(i) for i in data)
            if not data:
                break
            time.sleep(0.5)  # la API pide no abusar
        return jobs

    @staticmethod
    def _parse(item: dict) -> Job:
        return Job(
            id="arbeitnow:%s" % item["slug"],
            source="arbeitnow",
            title=(item.get("title") or "").strip(),
            company=(item.get("company_name") or "").strip(),
            url=item.get("url", ""),
            location=(item.get("location") or "").strip(),
            remote=bool(item.get("remote")),
            description=html_to_text(item.get("description", "")),
            tags=[str(t) for t in (item.get("tags") or [])] + [str(t) for t in (item.get("job_types") or [])],
            posted_at=iso_from_epoch(item.get("created_at")),
        )
