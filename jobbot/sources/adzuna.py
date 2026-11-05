"""Adzuna — requiere app_id/app_key gratuitos (https://developer.adzuna.com).

NOTA: implementado según la documentación pública de Adzuna pero NO verificado con credenciales
reales. Variables: ADZUNA_APP_ID, ADZUNA_APP_KEY, ADZUNA_COUNTRY (código de 2 letras, def. "us").
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional

from ..models import Job, Preferences, html_to_text
from .base import Source, search_queries


class Adzuna(Source):
    name = "adzuna"
    label = "Adzuna"
    homepage = "https://www.adzuna.com"
    requires_key = True

    def available(self) -> Optional[str]:
        if not (os.environ.get("ADZUNA_APP_ID") and os.environ.get("ADZUNA_APP_KEY")):
            return "faltan ADZUNA_APP_ID / ADZUNA_APP_KEY"
        return None

    def fetch(self, prefs: Preferences, client) -> List[Job]:
        country = os.environ.get("ADZUNA_COUNTRY", "us").lower()
        jobs: Dict[str, Job] = {}
        for query in search_queries(prefs):
            resp = client.get(
                "https://api.adzuna.com/v1/api/jobs/%s/search/1" % country,
                params={
                    "app_id": os.environ["ADZUNA_APP_ID"],
                    "app_key": os.environ["ADZUNA_APP_KEY"],
                    "what": query,
                    "results_per_page": 50,
                    "max_days_old": prefs.max_age_days,
                    "sort_by": "date",
                    "content-type": "application/json",
                },
            )
            resp.raise_for_status()
            for item in resp.json().get("results", []):
                job = self._parse(item)
                jobs.setdefault(job.id, job)
        return list(jobs.values())

    @staticmethod
    def _parse(item: dict) -> Job:
        lo, hi = item.get("salary_min"), item.get("salary_max")
        return Job(
            id="adzuna:%s" % item["id"],
            source="adzuna",
            title=html_to_text(item.get("title", "")),
            company=((item.get("company") or {}).get("display_name") or "").strip(),
            url=item.get("redirect_url", ""),
            location=((item.get("location") or {}).get("display_name") or "").strip(),
            remote=None,  # Adzuna no declara remoto de forma estructurada
            description=html_to_text(item.get("description", "")),
            posted_at=item.get("created", ""),
            salary=("%s-%s" % (int(lo), int(hi))) if lo and hi else "",
        )
