"""Construcción de preferencias: defaults derivados del perfil + wizard interactivo."""
from __future__ import annotations

import re
from typing import Callable, List, Optional

from .models import Preferences, Profile

WORLDWIDE_TERMS = ["worldwide", "anywhere", "global", "remote"]
LATAM_COUNTRIES = {
    "argentina", "brazil", "chile", "colombia", "mexico", "peru", "uruguay", "paraguay",
    "bolivia", "ecuador", "venezuela", "costa rica", "panama", "dominican republic",
    "guatemala", "el salvador", "honduras", "nicaragua",
}
LATAM_TERMS = ["latam", "latin america", "south america", "americas"]
EU_COUNTRIES = {
    "spain", "portugal", "germany", "france", "italy", "netherlands", "poland", "ireland",
    "belgium", "austria", "sweden", "denmark", "finland", "romania", "greece", "czechia",
}
EU_TERMS = ["europe", "emea", "eu"]

SENIORITY_ALIASES = {
    "jr": "junior", "junior": "junior",
    "ssr": "mid", "semi": "mid", "semi-senior": "mid", "semisenior": "mid", "mid": "mid",
    "middle": "mid", "mid-level": "mid",
    "sr": "senior", "senior": "senior",
    "lead": "lead", "staff": "lead", "principal": "lead", "tech lead": "lead",
}


DEFAULT_SENIORITY = {
    "junior": ["junior", "mid"],
    "mid": ["mid", "senior"],
    "senior": ["mid", "senior"],
    "lead": ["senior", "lead"],
}


def default_regions(country: str) -> List[str]:
    """Términos con los que las ofertas suelen describir regiones que incluyen a `country`."""
    regions = list(WORLDWIDE_TERMS)
    c = (country or "").strip().lower()
    if c:
        regions.append(c)
    if c in LATAM_COUNTRIES:
        regions += LATAM_TERMS
    elif c in EU_COUNTRIES:
        regions += EU_TERMS
    return regions


def split_list(text: str) -> List[str]:
    return [p.strip() for p in re.split(r"[,;\n]", text or "") if p.strip()]


def normalize_seniority(values: List[str]) -> List[str]:
    out: List[str] = []
    for v in values:
        level = SENIORITY_ALIASES.get(v.strip().lower())
        if level and level not in out:
            out.append(level)
    return out


def preferences_from_profile(profile: Profile) -> Preferences:
    """Defaults razonables a partir del perfil; el usuario los ajusta después."""
    prefs = Preferences()
    if profile.roles_suited:
        prefs.target_roles = list(profile.roles_suited[:3])
    prefs.seniority = list(DEFAULT_SENIORITY.get(profile.seniority_level, ["mid", "senior"]))
    prefs.candidate_country = profile.country
    prefs.eligible_regions = default_regions(profile.country)
    prefs.preferred_stack = list(profile.primary_stack[:6])
    return prefs


# (pregunta, getter, setter) ----------------------------------------------------------
Ask = Callable[[str, str], str]  # (pregunta, default) -> respuesta


def run_wizard(prefs: Preferences, ask: Ask, profile: Optional[Profile] = None) -> Preferences:
    """Pregunta cada preferencia mostrando el valor actual como default."""

    def lst(question: str, current: List[str]) -> List[str]:
        raw = ask(question, ", ".join(current))
        return [] if raw.strip() == "-" else split_list(raw)  # "-" borra la lista

    prefs.target_roles = lst("Puestos que buscás (separados por coma)", prefs.target_roles) or prefs.target_roles
    while True:
        raw = ask("Seniority (junior, ssr/mid, sr/senior, lead)", ", ".join(prefs.seniority))
        levels = normalize_seniority(split_list(raw))
        if levels:
            prefs.seniority = levels
            break
        print("  Valores válidos: junior, ssr/mid, sr/senior, lead")

    modes = ask("Modalidad (remote, hybrid, onsite)", ", ".join(prefs.work_modes))
    parsed = [m for m in split_list(modes.lower()) if m in ("remote", "hybrid", "onsite")]
    prefs.work_modes = parsed or prefs.work_modes

    old_country = prefs.candidate_country
    prefs.candidate_country = ask("País donde vivís (para saber a qué ofertas remotas podés aplicar)",
                                  prefs.candidate_country).strip()
    if prefs.candidate_country.lower() != (old_country or "").lower():
        prefs.eligible_regions = default_regions(prefs.candidate_country)
    prefs.eligible_regions = lst(
        "Regiones elegibles: términos que, si aparecen en la restricción geográfica de una oferta, "
        "te habilitan", prefs.eligible_regions) or prefs.eligible_regions

    prefs.preferred_stack = lst("Tecnologías que preferís (opcional)", prefs.preferred_stack)
    prefs.avoid_stack = lst("Tecnologías que querés evitar (opcional)", prefs.avoid_stack)
    prefs.exclude_keywords = lst(
        "Palabras a excluir del título (ej. intern, manager; opcional)", prefs.exclude_keywords)
    notes = ask("Notas libres para Claude (ej. 'prefiero startups', 'no fintech'; '-' para borrar)",
                prefs.notes).strip()
    prefs.notes = "" if notes == "-" else notes
    prefs.output_language = ask("Idioma de los resúmenes del reporte", prefs.output_language).strip() \
        or prefs.output_language
    return prefs
