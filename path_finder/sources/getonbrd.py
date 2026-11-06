"""Get on Board — API pública sin clave (https://www.getonbrd.com/api/v0). Foco LATAM, muchas ofertas en español."""
from __future__ import annotations

from typing import Dict, List

from .. import areas as areas_mod
from ..models import Job, Preferences, html_to_text
from .base import Source, iso_from_epoch, search_queries

SECTIONS = ("description", "functions", "desirable", "benefits")
CATEGORY_URL = "https://www.getonbrd.com/api/v0/categories/%s/jobs"
CATEGORY_PAGES = 3


def spanish_queries(prefs: Preferences) -> List[str]:
    """'Backend Engineer' -> 'desarrollador backend': los avisos en español rara vez dicen 'engineer'."""
    out: List[str] = []
    for q in search_queries(prefs):
        words = q.lower().split()
        if words and words[-1] in ("engineer", "developer") and len(words) > 1:
            out.append("desarrollador " + " ".join(words[:-1]))
    return out


class GetOnBoard(Source):
    name = "getonbrd"
    label = "Get on Board"
    homepage = "https://www.getonbrd.com"
    auto_languages = ("es",)
    URL = "https://www.getonbrd.com/api/v0/search/jobs"

    def fetch(self, prefs: Preferences, client) -> List[Job]:
        queries = search_queries(prefs)
        if "es" in prefs.job_languages:
            queries += spanish_queries(prefs)
        jobs: Dict[str, Job] = {}
        for query in queries:
            resp = client.get(self.URL, params={
                "query": query, "per_page": 100, "remote": "true", "expand": '["company","tags"]'})
            resp.raise_for_status()
            for item in resp.json().get("data", []):
                job = self._parse(item)
                jobs.setdefault(job.id, job)
        for category in dict.fromkeys(c for a in areas_mod.resolve(prefs.areas) for c in a.feeds.get("getonbrd", [])):
            for page in range(1, CATEGORY_PAGES + 1):
                resp = client.get(CATEGORY_URL % category, params={
                    "per_page": 100, "page": page, "expand": '["company","tags"]'})
                resp.raise_for_status()
                body = resp.json()
                for item in body.get("data", []):
                    job = self._parse(item)
                    jobs.setdefault(job.id, job)
                if page >= (body.get("meta") or {}).get("total_pages", 1):
                    break
        return list(jobs.values())

    @staticmethod
    def _parse(item: dict) -> Job:
        a = item.get("attributes", {})
        company = ((a.get("company") or {}).get("data") or {}).get("attributes", {}).get("name", "")
        tags = [t.get("attributes", {}).get("name", "") for t in (a.get("tags") or {}).get("data", [])
                if isinstance(t, dict) and t.get("attributes")]
        salary = ""
        if a.get("min_salary") or a.get("max_salary"):
            lo, hi = a.get("min_salary"), a.get("max_salary")
            salary = "US$%s-%s/mes" % (lo, hi) if lo and hi and lo != hi else "US$%s/mes" % (hi or lo)
        text = "\n\n".join(html_to_text(a.get(k) or "") for k in SECTIONS if a.get(k))
        lang = a.get("lang") if a.get("lang") in ("es", "en", "pt") else ""
        modality = a.get("remote_modality")
        return Job(
            id="getonbrd:%s" % item["id"],
            source="getonbrd",
            title=(a.get("title") or "").strip(),
            company=company.strip(),
            url=(item.get("links") or {}).get("public_url", ""),
            location=", ".join(a.get("countries") or []),
            # la categoría mezcla modalidades: fully_remote sí; remote_local (remoto dentro de un país) es desconocido
            remote=True if modality == "fully_remote" else None if modality == "remote_local" else False,
            description=text,
            tags=[t for t in tags if t],
            posted_at=iso_from_epoch(a.get("published_at")),
            salary=salary,
            language=lang,
        )
