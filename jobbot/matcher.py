"""Scoring de ofertas contra el perfil: Claude (por lotes) o heurística local (--no-llm)."""
from __future__ import annotations

import json
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

from .claude import Claude, ClaudeError
from .filters import contains_term
from .models import Job, Match, Preferences, Profile

MAX_DESC_CHARS = 3000
ELIGIBLE = ("yes", "no", "unclear")
FIT = ("below", "good", "above", "unclear")

MATCH_TOOL: Dict[str, Any] = {
    "name": "submit_matches",
    "description": "Devuelve la evaluación de cada oferta del lote.",
    "input_schema": {
        "type": "object",
        "properties": {
            "matches": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "description": "El id del lote (JOB 1 -> '1')"},
                        "score": {"type": "integer", "minimum": 0, "maximum": 100},
                        "eligible": {"type": "string", "enum": list(ELIGIBLE)},
                        "seniority_fit": {"type": "string", "enum": list(FIT)},
                        "summary": {"type": "string", "description": "1-2 oraciones: por qué sí o no"},
                        "reasons": {"type": "array", "items": {"type": "string"}, "maxItems": 4},
                        "gaps": {"type": "array", "items": {"type": "string"}, "maxItems": 4},
                    },
                    "required": ["id", "score", "eligible", "seniority_fit", "summary", "reasons", "gaps"],
                },
            }
        },
        "required": ["matches"],
    },
}

SYSTEM_TEMPLATE = """\
You are an expert technical recruiter helping ONE candidate find jobs. You receive the candidate's \
profile and search preferences, then batches of job postings. Evaluate each posting honestly.

CANDIDATE PROFILE (from their CV):
{profile}

SEARCH PREFERENCES:
{prefs}

For each job return:
- score (0-100): how good a match it is for this candidate. 85+ = excellent (stack, seniority, domain \
and conditions line up); 70-84 = strong; 55-69 = decent with notable gaps; <55 = weak. Weigh: required \
skills overlap with the candidate's REAL experience, seniority fit, preferred/avoided stack, domain, \
and work-mode fit. Be strict: do not inflate scores, and never credit skills the profile does not show.
- eligible: can this candidate actually apply from their country ({country})? "no" if the posting \
restricts location/work authorization/timezone in a way that excludes them (e.g. "US only", "must be \
based in Germany", US work authorization required); "yes" if it is worldwide or explicitly includes \
their region; "unclear" if the posting does not say. Use the structured location fields AND the \
description text.
- seniority_fit: "below" (role is more junior than the candidate wants), "good", "above" (clearly \
requires more seniority/experience than the candidate has), or "unclear".
- summary, reasons (why it fits, max 4 short points), gaps (missing requirements or concerns, max 4 \
short points): write them in {language}. Keep them concrete and specific to the posting.
Return one entry per job, using the batch id (JOB 1 -> "1")."""


def build_system(profile: Profile, prefs: Preferences) -> str:
    prefs_view = {
        "target_roles": prefs.target_roles,
        "seniority_wanted": prefs.seniority,
        "work_modes": prefs.work_modes,
        "country": prefs.candidate_country,
        "preferred_stack": prefs.preferred_stack,
        "avoid_stack": prefs.avoid_stack,
        "languages_ok": prefs.languages_ok,
        "min_salary_usd": prefs.min_salary_usd or None,
        "extra_notes": prefs.notes,
    }
    return SYSTEM_TEMPLATE.format(
        profile=json.dumps(profile.to_dict(), ensure_ascii=False, indent=1),
        prefs=json.dumps(prefs_view, ensure_ascii=False, indent=1),
        country=prefs.candidate_country or "unknown",
        language=prefs.output_language or "English",
    )


def format_job(index: int, job: Job) -> str:
    desc = job.description[:MAX_DESC_CHARS]
    if len(job.description) > MAX_DESC_CHARS:
        desc += " [...truncated]"
    return (
        "### JOB %d\nTitle: %s\nCompany: %s\nLocation: %s\nDeclared location restrictions: %s\n"
        "Remote: %s\nSalary: %s\nTags: %s\nPosted: %s\nDescription:\n%s\n"
        % (
            index, job.title, job.company, job.location or "n/a",
            ", ".join(job.location_restrictions) or "none declared",
            {True: "yes", False: "no", None: "unknown"}[job.remote],
            job.salary or "n/a", ", ".join(job.tags[:12]) or "n/a", job.posted_at or "n/a", desc,
        )
    )


def estimate_tokens(system: str, jobs: List[Job], batch_size: int) -> Tuple[int, int, int]:
    """(llamadas, tokens de entrada aprox., tokens de salida aprox.). ~4 caracteres por token."""
    calls = -(-len(jobs) // max(batch_size, 1))
    job_chars = sum(len(format_job(i, j)) for i, j in enumerate(jobs, 1))
    # El system va cacheado: se paga completo solo en la 1ª llamada (aprox.)
    return calls, (len(system) + job_chars) // 4 + 200 * calls, 220 * len(jobs)


def _clean(raw: Dict[str, Any], job: Job) -> Match:
    eligible = raw.get("eligible") if raw.get("eligible") in ELIGIBLE else "unclear"
    fit = raw.get("seniority_fit") if raw.get("seniority_fit") in FIT else "unclear"
    try:
        score = max(0, min(100, int(raw.get("score", 0))))
    except (TypeError, ValueError):
        score = 0
    if eligible == "no":
        score = min(score, 25)  # si no puede aplicar, no puede ser un buen match
    return Match(
        job_id=job.id, score=score, eligible=eligible, seniority_fit=fit,
        summary=str(raw.get("summary", "")).strip(),
        reasons=[str(r) for r in (raw.get("reasons") or [])][:4],
        gaps=[str(g) for g in (raw.get("gaps") or [])][:4],
        method="claude",
    )


def score_batch(claude: Claude, system: str, batch: List[Job]) -> Dict[str, Match]:
    user = "Evaluate these %d job postings.\n\n%s" % (
        len(batch), "\n".join(format_job(i, j) for i, j in enumerate(batch, 1))
    )
    out: Dict[str, Match] = {}
    for _attempt in range(2):  # un reintento si falta alguna oferta en la respuesta
        data = claude.tool_call(system, user, MATCH_TOOL, max_tokens=700 * len(batch))
        for raw in data.get("matches", []):
            m = re.search(r"\d+", str(raw.get("id", "")))
            if not m:
                continue
            idx = int(m.group()) - 1
            if 0 <= idx < len(batch):
                out[batch[idx].id] = _clean(raw, batch[idx])
        if len(out) == len(batch):
            break
    return out


def score_jobs(
    claude: Claude,
    profile: Profile,
    prefs: Preferences,
    jobs: List[Job],
    on_batch: Optional[Callable[[int, int], None]] = None,
) -> Tuple[List[Match], List[Job]]:
    """Puntúa por lotes. Devuelve (matches, ofertas que no se pudieron puntuar)."""
    system = build_system(profile, prefs)
    size = max(prefs.batch_size, 1)
    matches: List[Match] = []
    failed: List[Job] = []
    for start in range(0, len(jobs), size):
        batch = jobs[start : start + size]
        try:
            got = score_batch(claude, system, batch)
        except ClaudeError:
            got = {}
        matches.extend(got.values())
        failed.extend(j for j in batch if j.id not in got)
        if on_batch:
            on_batch(min(start + size, len(jobs)), len(jobs))
    return matches, failed


def _skill_in_text(text: str, skill: str) -> bool:
    if len(skill.strip()) <= 3:  # "Go", "Vue", "AWS": evitar falsos positivos con palabras comunes
        return re.search(r"(?<!\w)%s(?!\w)" % re.escape(skill.strip()), text) is not None
    return contains_term(text, skill)


def heuristic_match(job: Job, profile: Profile, prefs: Preferences) -> Match:
    """Score aproximado sin LLM: coincidencia de skills del perfil en el texto de la oferta."""
    text = " ".join([job.title, " ".join(job.tags), job.description])
    skills = {s for s in (profile.skills + profile.primary_stack) if len(s.strip()) >= 2}
    hits = sorted(s for s in skills if _skill_in_text(text, s))
    pref_hits = [s for s in prefs.preferred_stack if contains_term(text, s)]
    avoided = [s for s in prefs.avoid_stack if contains_term(text, s)]
    score = 25 + 7 * len(hits) + 5 * len(pref_hits) - 15 * len(avoided)
    if any(contains_term(job.title, w) for w in ("senior", "sr")) and "senior" in prefs.seniority:
        score += 8
    eligible = "yes" if job.location_restrictions else "unclear"
    return Match(
        job_id=job.id, score=max(0, min(100, score)), eligible=eligible,
        summary="Coincidencias de skills: %s. (Heurística sin Claude: es una aproximación.)"
        % (", ".join(hits[:8]) or "ninguna"),
        reasons=["Coincide con: %s" % ", ".join(hits[:8])] if hits else [],
        gaps=["Evita: %s" % ", ".join(avoided)] if avoided else [],
        method="heuristic",
    )
