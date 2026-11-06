"""Ranking de ofertas contra el perfil con reglas locales (sin IA ni red).

Score 0-100 = base + skills + imprescindibles + título + seniority + experiencia pedida + elegibilidad - penalizaciones. Los pesos salen del área principal.
Las reasons/gaps salen de plantillas. Es una guía para priorizar, no un veredicto.
"""
from __future__ import annotations

import re
from typing import Dict, List, Tuple

from . import areas as areas_mod
from .filters import active_areas, contains_term, role_forms_split, role_in_title
from .models import Job, Match, Preferences, Profile
from .roles import level_fit, title_level  # noqa: F401  (title_level se re-exporta)

BASE = 20
CAP_PRIMARY, CAP_OTHER, CAP_PREFERRED = 5, 5, 3
W_ELIGIBLE = 5
W_MUST = 12
P_MUST_MISSING, CAP_MUST_MISSING = 10, 20
P_AVOID = 15
P_ABOVE = 10
P_BELOW = 20
INELIGIBLE_CAP = 25
GENERIC_REGION_TERMS = {"remote", "global", "anywhere", "worldwide"}

REGION_NAMES = (
    r"us|u\.s\.|usa|united states|uk|u\.k\.|united kingdom|eu|europe|european union|emea|canada|"
    r"north america|germany|france|spain|italy|netherlands|ireland|poland|india|australia|brazil|mexico"
)
ONLY_RE = re.compile(r"(?<![\w-])(?P<region>%s)[- ]?(?:based )?(?:only|residents only|candidates only)\b" % REGION_NAMES)
MUST_RE = re.compile(
    r"\b(?:must|need to|required to|have to)\s+(?:be\s+)?(?:currently\s+)?(?:located|based|reside|residing|living|live)\s+"
    r"(?:in|within)\s+(?:the\s+)?(?P<region>[^.;:\n]{2,50})")
ONLY_IN_RE = re.compile(
    r"\bonly\s+(?:open to\s+|available to\s+|considering\s+)?(?:candidates|applicants|residents)?\s*"
    r"(?:who are\s+)?(?:located|based|living|residing)?\s*in\s+(?:the\s+)?(?P<region>[^.;:\n]{2,50})")
AUTH_RE = re.compile(
    r"(?:authori[sz]ed to work in|right to work in|work authori[sz]ation (?:for|in)|eligible to work in|"
    r"legally (?:able|entitled|authori[sz]ed) to work in)\s+(?:the\s+)?(?P<region>%s)\b" % REGION_NAMES)
WORLDWIDE_RE = re.compile(
    r"\b(worldwide|anywhere in the world|work from anywhere|from anywhere in the world|any country|"
    r"all countries|globally distributed|fully distributed)\b")
OVERLAP_RE = re.compile(r"\b(overlap|working hours|business hours)\b[^.\n]{0,40}\b(est|pst|cst|edt|pdt|cet|gmt|utc[+-]?\d*|eastern|pacific|central european)\b")
YEARS_RE = re.compile(
    r"(\d{1,2})\s*\+?\s*(?:or more\s+)?(?:years?|yrs?|años?)\b[^.\n]{0,40}?(?:experience|exp\b|experiencia)|"
    r"(?:experience|experiencia)[^.\n]{0,40}?(\d{1,2})\s*\+?\s*(?:years?|yrs?|años?)")
NUMBER_RE = re.compile(r"(\d[\d,.]*)\s*(k)?", re.I)


def _region_terms(prefs: Preferences) -> List[str]:
    terms = [t for t in prefs.eligible_regions if t.strip().lower() not in GENERIC_REGION_TERMS]
    if prefs.candidate_country:
        terms.append(prefs.candidate_country)
    return terms


def _mentions_region(text: str, terms: List[str]) -> bool:
    return any(contains_term(text, t) for t in terms)


def eligibility(job: Job, prefs: Preferences) -> Tuple[str, str]:
    """(yes|no|unclear, motivo). Usa restricciones estructuradas y patrones del texto de la oferta."""
    terms = _region_terms(prefs)
    if job.location_restrictions:
        text = ", ".join(job.location_restrictions)
        if any(contains_term(text, t) for t in prefs.eligible_regions):
            return "yes", "La oferta declara: %s" % text
        return "no", "Restricción geográfica declarada: %s" % text

    text = " ".join([job.title, job.location, job.description]).lower()
    for rx in (ONLY_RE, MUST_RE, ONLY_IN_RE, AUTH_RE):
        for m in rx.finditer(text):
            region = m.group("region")
            if not _mentions_region(region, terms):
                return "no", "El texto limita la ubicación a: %s" % region.strip()
    if _mentions_region(text, terms):
        return "yes", "Menciona tu región"
    if WORLDWIDE_RE.search(text):
        return "yes", "Dice ser remoto desde cualquier lugar"
    return "unclear", "La oferta no aclara desde dónde se puede aplicar"


def required_years(text: str) -> int:
    """Mayor cantidad de años de experiencia pedida en el texto (0 si no la detecta)."""
    values = []
    for m in YEARS_RE.finditer(text.lower()):
        n = int(m.group(1) or m.group(2))
        if 1 <= n <= 25:
            values.append(n)
    return max(values) if values else 0


def salary_max(salary: str) -> int:
    best = 0
    for num, k in NUMBER_RE.findall(salary or ""):
        digits = num.replace(",", "").replace(".", "")
        if not digits.isdigit():
            continue
        value = int(digits) * (1000 if k else 1)
        best = max(best, value)
    return best


def rank_job(job: Job, profile: Profile, prefs: Preferences) -> Match:
    w = active_areas(profile, prefs)[0].weights  # pesos del área principal
    text = " ".join([job.title, " ".join(job.tags), job.description])
    primary = [s for s in profile.primary_stack if _has(text, s)]
    others = [s for s in profile.skills if s not in profile.primary_stack and _has(text, s)]
    preferred = [s for s in prefs.preferred_stack
                 if s not in profile.primary_stack and s not in profile.skills and _has(text, s)]
    avoided = [s for s in prefs.avoid_stack if _has(text, s)]
    musts_hit = [s for s in prefs.must_have if _has(text, s)]
    musts_missing = [s for s in prefs.must_have if s not in musts_hit]

    score = BASE
    score += w["primary"] * min(len(primary), CAP_PRIMARY)
    score += w["other"] * min(len(others), CAP_OTHER)
    score += w["preferred"] * min(len(preferred), CAP_PREFERRED)
    score += W_MUST * len(musts_hit)
    reasons: List[str] = []
    gaps: List[str] = []
    if primary:
        reasons.append("Tus skills principales: %s" % ", ".join(primary))
    if others or preferred:
        reasons.append("También coincide: %s" % ", ".join((others + preferred)[:6]))
    if musts_hit:
        reasons.append("Menciona tus imprescindibles: %s" % ", ".join(musts_hit))
    if musts_missing:
        score -= min(P_MUST_MISSING * len(musts_missing), CAP_MUST_MISSING)
        gaps.append("No menciona tus imprescindibles: %s" % ", ".join(musts_missing))

    phrases, shorts = role_forms_split(prefs)
    if role_in_title(job.title, phrases, shorts):
        score += w["title"]
        reasons.append("El título coincide con lo que buscás")

    # seniority: rango buscado vs nivel del título
    level = title_level(job.title)
    fit, steps = level_fit(level, prefs.seniority)
    if fit == "good":
        score += w["seniority"]
        reasons.append("Seniority del título: %s" % level)
    elif fit == "below":
        score -= P_BELOW
        gaps.append("Parece más junior de lo que buscás (%s)" % level)
    elif fit == "above":
        score -= min(P_ABOVE * steps, 2 * P_ABOVE)
        gaps.append("Parece pedir más seniority (%s)" % level)

    # años pedidos
    need = required_years(job.description)
    have = profile.years_experience or 0
    if need and have:
        if need > have + 4:
            score -= 2 * P_ABOVE
            fit = "above"
            gaps.append("Pide %d+ años de experiencia; el perfil tiene ~%g" % (need, have))
        elif need > have + 1:
            score -= P_ABOVE
            gaps.append("Pide %d+ años de experiencia; el perfil tiene ~%g" % (need, have))
        elif fit == "unclear":
            fit = "good"
    elif need and not have:
        gaps.append("Pide %d+ años de experiencia" % need)

    if avoided:
        score -= P_AVOID * len(avoided)
        gaps.append("Menciona algo que querés evitar: %s" % ", ".join(avoided))

    if prefs.min_salary_usd and job.salary:
        top = salary_max(job.salary)
        if 1000 <= top < prefs.min_salary_usd:
            score -= P_ABOVE
            gaps.append("Salario declarado (%s) bajo tu mínimo" % job.salary)

    if OVERLAP_RE.search(text.lower()):
        gaps.append("Pide solapamiento de horario: verificalo")

    eligible, why = eligibility(job, prefs)
    if eligible == "yes":
        score += W_ELIGIBLE
    elif eligible == "no":
        score = min(score, INELIGIBLE_CAP)
        gaps.append(why)
    else:
        gaps.append("Verificá desde dónde se puede aplicar")

    hits = len(primary) + len(others) + len(preferred) + len(musts_hit)
    summary = "%d coincidencias de skills/términos con tu perfil. %s." % (hits, why)
    return Match(
        job_id=job.id, score=max(0, min(100, score)), eligible=eligible, seniority_fit=fit,
        summary=summary, reasons=reasons[:4], gaps=gaps[:4],
    )


def rank_jobs(jobs: List[Job], profile: Profile, prefs: Preferences) -> Dict[str, Match]:
    return {j.id: rank_job(j, profile, prefs) for j in jobs}


def _has(text: str, skill: str) -> bool:
    skill = skill.strip()
    if len(skill) < 2:
        return False
    skills, _concepts, ambiguous = areas_mod.vocabulary()
    return any(_has_one(text, name, ambiguous) for name in [skill] + skills.get(skill, []))


def _has_one(text: str, name: str, ambiguous=frozenset()) -> bool:
    if len(name) <= 3 or name in ambiguous:  # "Go", "AWS", "Gin": respetar mayúsculas para evitar palabras comunes
        return re.search(r"(?<![\w+#])%s(?![\w+#])" % re.escape(name), text) is not None
    return contains_term(text, name)
