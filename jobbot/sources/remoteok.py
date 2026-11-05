"""Remote OK — feed JSON público sin clave (últimas ~100 ofertas). Atribución obligatoria."""
from __future__ import annotations

from typing import List

from ..models import Job, Preferences, html_to_text
from .base import Source


class RemoteOK(Source):
    name = "remoteok"
    label = "Remote OK"
    homepage = "https://remoteok.com"
    URL = "https://remoteok.com/api"

    def fetch(self, prefs: Preferences, client) -> List[Job]:
        resp = client.get(self.URL)
        resp.raise_for_status()
        # El primer elemento es el aviso legal, no una oferta
        return [self._parse(i) for i in resp.json() if isinstance(i, dict) and i.get("id")]

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
