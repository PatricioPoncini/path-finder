"""Remotive — API pública sin clave (https://remotive.com/api/remote-jobs). Atribución obligatoria."""
from __future__ import annotations

from typing import Dict, List

from ..models import Job, Preferences, html_to_text
from .base import Source, search_queries


class Remotive(Source):
    name = "remotive"
    label = "Remotive"
    homepage = "https://remotive.com"
    URL = "https://remotive.com/api/remote-jobs"

    def fetch(self, prefs: Preferences, client) -> List[Job]:
        jobs: Dict[str, Job] = {}
        for query in search_queries(prefs):
            resp = client.get(self.URL, params={"search": query, "limit": 100})
            resp.raise_for_status()
            for item in resp.json().get("jobs", []):
                job = self._parse(item)
                jobs.setdefault(job.id, job)
        return list(jobs.values())

    @staticmethod
    def _parse(item: dict) -> Job:
        location = (item.get("candidate_required_location") or "").strip()
        return Job(
            id="remotive:%s" % item["id"],
            source="remotive",
            title=(item.get("title") or "").strip(),
            company=(item.get("company_name") or "").strip(),
            url=item.get("url", ""),
            location=location,
            location_restrictions=[location] if location else [],
            remote=True,
            description=html_to_text(item.get("description", "")),
            tags=[str(t) for t in (item.get("tags") or [])],
            posted_at=(item.get("publication_date") or "") and (item["publication_date"] + "+00:00"),
            salary=(item.get("salary") or "").strip(),
        )
