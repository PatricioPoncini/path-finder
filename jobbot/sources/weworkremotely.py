"""We Work Remotely — feeds RSS públicos por categoría."""
from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import timezone
from email.utils import parsedate_to_datetime
from typing import Dict, List

from ..models import Job, Preferences, html_to_text, stable_hash
from .base import Source

FEEDS = [
    "https://weworkremotely.com/remote-jobs.rss",
    "https://weworkremotely.com/categories/remote-programming-jobs.rss",
    "https://weworkremotely.com/categories/remote-back-end-programming-jobs.rss",
    "https://weworkremotely.com/categories/remote-full-stack-programming-jobs.rss",
    "https://weworkremotely.com/categories/remote-devops-sysadmin-jobs.rss",
]
WORLDWIDE = ("anywhere", "worldwide", "global")


def _text(item: ET.Element, tag: str) -> str:
    el = item.find(tag)
    return (el.text or "").strip() if el is not None and el.text else ""


class WeWorkRemotely(Source):
    name = "weworkremotely"
    label = "We Work Remotely"
    homepage = "https://weworkremotely.com"

    def fetch(self, prefs: Preferences, client) -> List[Job]:
        jobs: Dict[str, Job] = {}
        for url in FEEDS:
            resp = client.get(url)
            resp.raise_for_status()
            for job in self.parse_feed(resp.text):
                jobs.setdefault(job.id, job)
        return list(jobs.values())

    @staticmethod
    def parse_feed(xml_text: str) -> List[Job]:
        root = ET.fromstring(xml_text)
        jobs: List[Job] = []
        for item in root.iter("item"):
            raw_title = _text(item, "title")
            company, sep, title = raw_title.partition(": ")
            if not sep:
                company, title = "", raw_title
            region = _text(item, "region")
            country = _text(item, "country")
            restrictions = [] if (not region or any(w in region.lower() for w in WORLDWIDE)) else [region]
            if country and country not in restrictions:
                restrictions.append(country)
            try:
                posted = parsedate_to_datetime(_text(item, "pubDate")).astimezone(timezone.utc).isoformat(timespec="seconds")
            except (TypeError, ValueError):
                posted = ""
            guid = _text(item, "guid") or _text(item, "link")
            jobs.append(Job(
                id="weworkremotely:%s" % stable_hash(guid)[:10],
                source="weworkremotely",
                title=title.strip(),
                company=company.strip(),
                url=_text(item, "link") or guid,
                location=", ".join(restrictions) or "Anywhere in the World",
                location_restrictions=restrictions,
                remote=True,
                description=html_to_text(_text(item, "description")),
                tags=[t for t in (_text(item, "category"), _text(item, "type"), _text(item, "skills")) if t],
                posted_at=posted,
            ))
        return jobs
