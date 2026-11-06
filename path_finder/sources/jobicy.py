"""Jobicy — API pública sin clave (https://jobi.cy/apidocs). Exige acreditar a Jobicy con link a la oferta original."""
from __future__ import annotations

import re
from typing import Dict, List

from ..models import Job, Preferences, html_to_text
from .base import Source, search_queries

WORLDWIDE = ("anywhere", "worldwide", "global", "all countries")


def _list(value) -> List[str]:
    """Jobicy manda listas reales (['Software Engineering']) y a veces texto ("['A']" o "A, B")."""
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if str(v).strip()]
    text = value or ""
    return re.findall(r"'([^']+)'", text) if "'" in text else [v.strip() for v in text.split(",") if v.strip()]


class Jobicy(Source):
    name = "jobicy"
    label = "Jobicy"
    homepage = "https://jobicy.com"
    URL = "https://jobicy.com/api/v2/remote-jobs"

    def fetch(self, prefs: Preferences, client) -> List[Job]:
        jobs: Dict[str, Job] = {}
        for tag in [None] + search_queries(prefs):  # últimas ofertas + una consulta por rol buscado
            params = {"count": 100}
            if tag:
                params["tag"] = tag
            resp = client.get(self.URL, params=params)
            resp.raise_for_status()
            for item in resp.json().get("jobs", []):
                job = self._parse(item)
                jobs.setdefault(job.id, job)
        return list(jobs.values())

    @staticmethod
    def _parse(item: dict) -> Job:
        geo = _list(item.get("jobGeo"))
        restrictions = [] if any(w in g.lower() for g in geo for w in WORLDWIDE) else geo
        level = item.get("jobLevel") or ""
        tags = _list(item.get("jobIndustry", "")) + _list(item.get("jobType", "")) + ([level] if level and level != "Any" else [])
        return Job(
            id="jobicy:%s" % item["id"],
            source="jobicy",
            title=html_to_text(item.get("jobTitle", "")).strip(),
            company=(item.get("companyName") or "").strip(),
            url=item.get("url", ""),
            location=", ".join(geo) or "Anywhere",
            location_restrictions=restrictions,
            remote=True,
            description=html_to_text(item.get("jobDescription") or item.get("jobExcerpt", "")),
            tags=tags,
            posted_at=item.get("pubDate", ""),
        )
