"""Working Nomads — feed JSON público sin clave (últimas ~30 ofertas remotas)."""
from __future__ import annotations

import re
from typing import List

from ..models import Job, Preferences, html_to_text, stable_hash
from .base import Source

WORLDWIDE = ("anywhere", "worldwide", "global")


class WorkingNomads(Source):
    name = "workingnomads"
    label = "Working Nomads"
    homepage = "https://www.workingnomads.com"
    URL = "https://www.workingnomads.com/api/exposed_jobs/"

    def fetch(self, prefs: Preferences, client) -> List[Job]:
        resp = client.get(self.URL)
        resp.raise_for_status()
        return [self._parse(i) for i in resp.json() if isinstance(i, dict) and i.get("url")]

    @staticmethod
    def _parse(item: dict) -> Job:
        url = item["url"]
        m = re.search(r"/go/(\d+)", url) or re.search(r"/(\d+)/?$", url)
        location = (item.get("location") or "").strip()
        restricted = bool(location) and not any(w in location.lower() for w in WORLDWIDE)
        tags = [t.strip() for t in (item.get("tags") or "").split(",") if t.strip()]
        if item.get("category_name"):
            tags.append(item["category_name"])
        return Job(
            id="workingnomads:%s" % (m.group(1) if m else stable_hash(url)[:10]),
            source="workingnomads",
            title=(item.get("title") or "").strip(),
            company=(item.get("company_name") or "").strip(),
            url=url,
            location=location or "Anywhere",
            location_restrictions=[location] if restricted else [],
            remote=True,
            description=html_to_text(item.get("description", "")),
            tags=tags,
            posted_at=item.get("pub_date", ""),
        )
