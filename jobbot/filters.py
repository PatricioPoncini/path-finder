"""Pre-filtro barato (sin LLM): descarta lo obvio antes de gastar tokens."""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Set

from .models import Job, Preferences, Profile
from .sources.base import SENIORITY_WORDS

JUNIOR_RE = re.compile(r"\b(junior|jr\.?|intern(ship)?|trainee|entry[- ]level|graduate|apprentice)\b", re.I)
DEV_WORDS = ("engineer", "developer", "programmer", "software", "architect")
SWAPS = (("engineer", "developer"), ("developer", "engineer"))


@dataclass
class FilterResult:
    kept: List[Job] = field(default_factory=list)
    dropped: Counter = field(default_factory=Counter)  # motivo -> cantidad


def contains_term(text: str, term: str) -> bool:
    term = term.strip().lower()
    return bool(term) and re.search(r"(?<!\w)%s(?!\w)" % re.escape(term), text.lower()) is not None


def role_phrases(prefs: Preferences) -> Set[str]:
    """Frases aceptadas en el título: roles objetivo sin seniority (+ variantes engineer/developer)."""
    phrases: Set[str] = set()
    for role in list(prefs.target_roles) + list(prefs.title_keywords):
        words = [w for w in role.lower().split() if w not in SENIORITY_WORDS]
        base = " ".join(words).strip()
        if not base:
            continue
        phrases.add(base)
        for a, b in SWAPS:
            if a in base:
                phrases.add(base.replace(a, b))
    return phrases


def stack_terms(profile: Optional[Profile], prefs: Preferences) -> List[str]:
    terms = list(prefs.preferred_stack) + (list(profile.primary_stack) if profile else [])
    return [t.lower() for t in terms if len(t.strip()) >= 2]


def title_matches(job: Job, phrases: Set[str], stack: List[str]) -> bool:
    title = job.title.lower()
    if any(p in title for p in phrases):
        return True
    # "Go Developer", "Kotlin Engineer": rol genérico de desarrollo + tecnología conocida en el título
    return any(w in title for w in DEV_WORDS) and any(contains_term(title, s) for s in stack)


def parse_date(value: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def region_ok(job: Job, prefs: Preferences) -> bool:
    """¿Las restricciones geográficas declaradas dejan aplicar al candidato?"""
    if not job.location_restrictions:
        return True
    text = ", ".join(job.location_restrictions)
    return any(contains_term(text, t) for t in prefs.eligible_regions)


def normalize_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def apply_filters(
    jobs: List[Job], profile: Optional[Profile], prefs: Preferences, now: Optional[datetime] = None
) -> FilterResult:
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=prefs.max_age_days) if prefs.max_age_days else None
    phrases = role_phrases(prefs)
    stack = stack_terms(profile, prefs)
    want_junior = "junior" in prefs.seniority
    only_remote = prefs.work_modes == ["remote"]
    want_remote = "remote" in prefs.work_modes

    result = FilterResult()
    seen_ids: Set[str] = set()
    seen_keys: Set[str] = set()
    for job in jobs:
        if not job.title or not job.url:
            result.dropped["datos incompletos"] += 1
            continue
        if job.id in seen_ids:
            result.dropped["duplicada"] += 1
            continue
        seen_ids.add(job.id)

        key = "%s|%s" % (job.company.lower().strip(), normalize_title(job.title))
        if key in seen_keys:
            result.dropped["duplicada (misma empresa y título)"] += 1
            continue
        seen_keys.add(key)

        if only_remote and job.remote is False:
            result.dropped["no remota"] += 1
        elif not want_remote and job.remote is True:
            result.dropped["remota (no la querés)"] += 1
        elif cutoff and (posted := parse_date(job.posted_at)) and posted < cutoff:
            result.dropped["muy antigua"] += 1
        elif not title_matches(job, phrases, stack):
            result.dropped["título no coincide con tus roles"] += 1
        elif not want_junior and JUNIOR_RE.search(job.title):
            result.dropped["nivel junior/intern"] += 1
        elif any(contains_term(job.title + " " + " ".join(job.tags), k) for k in prefs.exclude_keywords):
            result.dropped["palabra excluida"] += 1
        elif prefs.strict_region_filter and not region_ok(job, prefs):
            result.dropped["restricción geográfica"] += 1
        else:
            result.kept.append(job)
    return result
