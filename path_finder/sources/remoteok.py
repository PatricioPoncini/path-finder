"""Remote OK — feed JSON público sin clave (últimas ~100 ofertas). Atribución obligatoria."""
from __future__ import annotations

from typing import List

from .. import areas as areas_mod
from ..models import Job, Preferences, html_to_text
from .base import Source


class RemoteOK(Source):
    name = "remoteok"
    label = "Remote OK"
    homepage = "https://remoteok.com"
    URL = "https://remoteok.com/api"

    def fetch(self, prefs: Preferences, client) -> List[Job]:
        jobs = {}
        tags = [None] + [t for a in areas_mod.resolve(prefs.areas) for t in a.feeds.get("remoteok_tags", [])]
        for tag in dict.fromkeys(tags):  # feed general + una consulta por tag de las áreas activas
            resp = client.get(self.URL, params={"tag": tag} if tag else None)
            resp.raise_for_status()
            # El primer elemento es el aviso legal, no una oferta
            for i in resp.json():
                if isinstance(i, dict) and i.get("id"):
                    job = self._parse(i)
                    jobs.setdefault(job.id, job)
        return list(jobs.values())

    @staticmethod
    def _parse(item: dict) -> Job:
        lo, hi = int(item.get("salary_min") or 0), int(item.get("salary_max") or 0)
        salary = ("$%s-%s" % (format(lo, ","), format(hi, ","))) if hi else ""
        return Job(
            id="remoteok:%s" % item["id"],
            source="remoteok",
            title=html_to_text(item.get("position", "")),
            company=(item.get("company") or "").strip(),
            url=item.get("url") or item.get("apply_url", ""),
            # La "location" de Remote OK es poco fiable como restricción: va solo como dato
            location=(item.get("location") or "").strip(),
            remote=True,
            description=html_to_text(item.get("description", "")),
            tags=[str(t) for t in (item.get("tags") or [])],
            posted_at=item.get("date", ""),
            salary=salary,
        )
