"""Himalayas — API pública sin clave (búsqueda paginada de 20 en 20)."""
from __future__ import annotations

from typing import Dict, List

from ..models import Job, Preferences, html_to_text, stable_hash
from .base import Source, iso_from_epoch, search_queries

PAGES_PER_QUERY = 3


class Himalayas(Source):
    name = "himalayas"
    label = "Himalayas"
    homepage = "https://himalayas.app"
    URL = "https://himalayas.app/jobs/api/search"

    def fetch(self, prefs: Preferences, client) -> List[Job]:
        jobs: Dict[str, Job] = {}
        for query in search_queries(prefs):
            for page in range(1, PAGES_PER_QUERY + 1):
                resp = client.get(self.URL, params={"q": query, "page": page})
                resp.raise_for_status()
                items = resp.json().get("jobs", [])
                for item in items:
                    job = self._parse(item)
                    jobs.setdefault(job.id, job)
                if len(items) < 20:
                    break
        return list(jobs.values())

    @staticmethod
    def _parse(item: dict) -> Job:
        restrictions = [str(r) for r in (item.get("locationRestrictions") or [])]
        lo, hi = item.get("minSalary"), item.get("maxSalary")
        salary = ""
        if hi:
            salary = "%s%s-%s/%s" % (item.get("currency") or "", lo or "", hi, item.get("salaryPeriod") or "")
        link = item.get("applicationLink") or item.get("guid", "")
        return Job(
            id="himalayas:%s" % stable_hash(item.get("guid") or link)[:10],
            source="himalayas",
            title=(item.get("title") or "").strip(),
            company=(item.get("companyName") or "").strip(),
            url=link,
            location=", ".join(restrictions) or "Worldwide",
            location_restrictions=restrictions,
            remote=True,
            description=html_to_text(item.get("description") or item.get("excerpt", "")),
            tags=[str(c) for c in (item.get("categories") or [])] + [str(s) for s in (item.get("seniority") or [])],
            posted_at=iso_from_epoch(item.get("pubDate")),
            salary=salary,
        )
