"""Pre-filtro barato (sin LLM): descarta lo obvio antes de gastar tokens."""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Set, Tuple

from . import areas as areas_mod
from .lang import detect_language, normalize_languages
from .models import Job, Preferences, Profile
from .roles import role_names
from .sources.base import SENIORITY_WORDS

JUNIOR_RE = re.compile(r"\b(junior|jr\.?|intern(ship)?|trainee|entry[- ]level|graduate|apprentice)\b", re.I)
COMPOUND_RE = re.compile(r"\b(back|front|full)[- ](end|stack)\b")
ES_NOUNS = ("desarrollador", "ingeniero")
SWAPS = (("engineer", "developer"), ("developer", "engineer"))


@dataclass
class FilterResult:
    kept: List[Job] = field(default_factory=list)
    dropped: Counter = field(default_factory=Counter)  # motivo -> cantidad


def contains_term(text: str, term: str) -> bool:
    term = term.strip().lower()
    return bool(term) and re.search(r"(?<!\w)%s(?!\w)" % re.escape(term), text.lower()) is not None


def norm_title(text: str) -> str:
    """Minúsculas y 'back-end' == 'backend' (también 'full stack' == 'fullstack')."""
    return COMPOUND_RE.sub(r"\1\2", text.lower())


def active_areas(profile: Optional[Profile], prefs: Preferences) -> List["areas_mod.Area"]:
    """Áreas elegidas en las preferencias o, si no hay, las del perfil (por defecto: tech)."""
    return areas_mod.resolve(prefs.areas or (profile.areas if profile else []))


def _expand(base: str, spanish: bool) -> Set[str]:
    out = {base}
    for a, b in SWAPS:
        if a in base:
            out.add(base.replace(a, b))
    words = base.split()
    if spanish and words and words[-1] in ("engineer", "developer"):
        rest = " ".join(words[:-1])  # "backend engineer" -> "desarrollador backend", "ingeniero de software"
        for noun in ES_NOUNS:
            out.add("%s %s" % (noun, rest) if rest else noun)
            out.add("%s de %s" % (noun, rest))
    return out


def _role_forms(role: str) -> List[str]:
    """Formas aceptadas de un rol: si está en el catálogo, título + alias; si no, sin palabras de seniority."""
    known = role_names(role)
    if len(known) > 1:
        return known
    stripped = " ".join(w for w in role.split() if w.lower() not in SENIORITY_WORDS)
    if stripped and stripped.lower() != role.lower():
        inner = role_names(stripped)
        if len(inner) > 1:
            return inner
    return [stripped or role]


def role_forms_split(prefs: Preferences) -> Tuple[Set[str], Set[str]]:
    """(frases en minúscula, alias cortos tipo PM/PO/TL que exigen mayúsculas exactas)."""
    spanish = "es" in normalize_languages(prefs.job_languages)
    phrases: Set[str] = set()
    shorts: Set[str] = set()
    for role in list(prefs.target_roles) + list(prefs.title_keywords):
        for form in _role_forms(role):
            if len(form) <= 3 and form.isupper():
                shorts.add(form)
                continue
            base = " ".join(w for w in norm_title(form).split() if w)
            if base:
                phrases |= _expand(base, spanish)
    return phrases, shorts


def role_phrases(prefs: Preferences) -> Set[str]:
    """Frases (minúsculas) aceptadas en el título para los roles buscados."""
    return role_forms_split(prefs)[0]


def stack_terms(profile: Optional[Profile], prefs: Preferences) -> List[str]:
    terms = list(prefs.preferred_stack) + list(prefs.must_have) + (list(profile.primary_stack) if profile else [])
    return [t.lower() for t in terms if len(t.strip()) >= 2]


def role_in_title(title: str, phrases: Set[str], shorts: Set[str]) -> bool:
    low = norm_title(title)
    if any(p in low for p in phrases):
        return True
    return any(re.search(r"(?<![A-Za-z])%s(?![A-Za-z])" % re.escape(s), title) for s in shorts)


def title_matches(job: Job, phrases: Set[str], stack: List[str], nouns: Optional[List[str]] = None,
                  shorts: Optional[Set[str]] = None) -> bool:
    if role_in_title(job.title, phrases, shorts or set()):
        return True
    # "Go Developer", "Kotlin Engineer", "Fintech Product Manager": sustantivo del área + término conocido en el título
    title = norm_title(job.title)
    nouns = nouns if nouns is not None else areas_mod.resolve(None)[0].title_nouns
    return any(w in title for w in nouns) and any(contains_term(title, s) for s in stack)


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


def job_language(job: Job) -> str:
    """Idioma de la descripción: detectado del texto; si no alcanza, el que declara la fuente."""
    return detect_language(job.description) or detect_language(job.title + ". " + job.description) or job.language


def normalize_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def apply_filters(
    jobs: List[Job], profile: Optional[Profile], prefs: Preferences, now: Optional[datetime] = None
) -> FilterResult:
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=prefs.max_age_days) if prefs.max_age_days else None
    phrases, shorts = role_forms_split(prefs)
    stack = stack_terms(profile, prefs)
    nouns = sorted({n for a in active_areas(profile, prefs) for n in a.title_nouns})
    want_junior = "junior" in prefs.seniority
    only_remote = prefs.work_modes == ["remote"]
    want_remote = "remote" in prefs.work_modes
    languages = set(normalize_languages(prefs.job_languages))

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
        elif not title_matches(job, phrases, stack, nouns, shorts):
            result.dropped["título no coincide con tus roles"] += 1
        elif not want_junior and JUNIOR_RE.search(job.title):
            result.dropped["nivel junior/intern"] += 1
        elif any(contains_term(job.title + " " + " ".join(job.tags), k) for k in prefs.exclude_keywords):
            result.dropped["palabra excluida"] += 1
        elif prefs.strict_region_filter and not region_ok(job, prefs):
            result.dropped["restricción geográfica"] += 1
        elif languages and (lang := job_language(job)) and lang not in languages:
            result.dropped["idioma de la oferta (%s)" % lang] += 1
        else:
            result.kept.append(job)
    return result
