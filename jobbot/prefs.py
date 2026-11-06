"""Construcción de preferencias: defaults derivados del perfil + wizard interactivo."""
from __future__ import annotations

import re
from typing import Callable, List, Optional

from .lang import LANGUAGE_NAMES, normalize_languages
from . import areas as areas_mod
from .models import Preferences, Profile
from .roles import LEVEL_INDEX, PRESETS, Preset, normalize_levels, resolve_roles

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

DEFAULT_SENIORITY = {
    "junior": ["junior", "mid"],
    "mid": ["mid", "senior"],
    "senior": ["mid", "senior"],
    "lead": ["senior", "lead"],
    "expert": ["senior", "lead", "expert"],
    "head": ["lead", "head"],
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
    return normalize_levels(values)


def preferences_from_profile(profile: Profile) -> Preferences:
    """Defaults razonables a partir del perfil; el usuario los ajusta después."""
    prefs = Preferences()
    if profile.roles_suited:
        prefs.target_roles = list(profile.roles_suited[:3])
    prefs.seniority = list(DEFAULT_SENIORITY.get(profile.seniority_level, ["mid", "senior"]))
    prefs.candidate_country = profile.country
    prefs.areas = list(profile.areas)
    prefs.eligible_regions = default_regions(profile.country)
    prefs.preferred_stack = list(profile.primary_stack[:6])
    return prefs


# (pregunta, getter, setter) ----------------------------------------------------------
Ask = Callable[[str, str], str]  # (pregunta, default) -> respuesta


def menu_presets(area_ids: List[str]) -> List[Preset]:
    """Roles comunes de las áreas elegidas (todos si no hay ninguna)."""
    chosen = [p for p in PRESETS if p.area in area_ids] if area_ids else list(PRESETS)
    return chosen or list(PRESETS)


def pick_roles(tokens: List[str], menu: List[Preset]):
    """Convierte respuestas ('2', 'Sr PM', 'Data Analyst') en (títulos, niveles explícitos, áreas)."""
    resolved: List[str] = []
    for t in tokens:
        if t.isdigit() and 1 <= int(t) <= len(menu):
            resolved.append(menu[int(t) - 1].label)
        else:
            resolved.append(t)
    titles, levels, areas = resolve_roles(resolved)
    any_unleveled = any(not resolve_roles([r])[1] for r in resolved)
    return titles, levels, areas, any_unleveled


def run_wizard(prefs: Preferences, ask: Ask, profile: Optional[Profile] = None) -> Preferences:
    """Pregunta cada preferencia mostrando el valor actual como default."""

    def lst(question: str, current: List[str]) -> List[str]:
        raw = ask(question, ", ".join(current))
        return [] if raw.strip() == "-" else split_list(raw)  # "-" borra la lista

    known = areas_mod.load_areas()
    while True:
        raw = ask("Áreas (%s)" % ", ".join(known), ", ".join(prefs.areas))
        chosen = [a for a in split_list(raw.lower()) if a in known]
        if chosen or not raw.strip():
            prefs.areas = chosen or prefs.areas
            break
        print("  Áreas válidas: %s" % ", ".join(known))

    menu = menu_presets(prefs.areas)
    print("Roles comunes (podés escribir números, siglas como PM/PO/TL o texto libre):")
    for i, p in enumerate(menu, 1):
        print("  %2d. %s" % (i, p.label))
    raw = ask("Puestos que buscás (números del menú o texto, separados por coma)", ", ".join(prefs.target_roles))
    titles, levels, found_areas, unleveled = pick_roles(split_list(raw), menu)
    if titles:
        prefs.target_roles = titles
        if levels:  # "Sr PM" fija el nivel; si algún rol no trae nivel, se conserva el que ya estaba
            prefs.seniority = sorted(set(levels) | (set(prefs.seniority) if unleveled else set()),
                                     key=lambda x: LEVEL_INDEX[x])
        prefs.areas = prefs.areas or found_areas
    while True:
        raw = ask("Seniority (junior, ssr/mid, sr/senior, lead/TL, expert/staff, head)", ", ".join(prefs.seniority))
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

    while True:
        raw = ask("Idioma de las ofertas que aceptás (es, en, pt…; '-' = cualquiera). "
                  "Con 'es' se suman sitios en español", ", ".join(prefs.job_languages))
        if raw.strip() == "-":
            prefs.job_languages = []
            break
        langs = normalize_languages(split_list(raw))
        if langs or not raw.strip():
            prefs.job_languages = langs or prefs.job_languages
            break
        print("  Idiomas válidos: %s" % ", ".join("%s (%s)" % (c, n) for c, n in LANGUAGE_NAMES.items()))

    prefs.must_have = lst("Imprescindibles: términos que la oferta debería mencionar (opcional)", prefs.must_have)
    prefs.preferred_stack = lst("Skills/tecnologías que preferís (opcional)", prefs.preferred_stack)
    prefs.avoid_stack = lst("Skills/tecnologías que querés evitar (opcional)", prefs.avoid_stack)
    prefs.exclude_keywords = lst(
        "Palabras a excluir del título (ej. intern, manager; opcional)", prefs.exclude_keywords)
    return prefs


def review_profile(profile: Profile, ask: Ask) -> Profile:
    """La extracción del CV es aproximada: deja corregir lo detectado."""

    def lst(question: str, current: List[str]) -> List[str]:
        raw = ask(question, ", ".join(current))
        return [] if raw.strip() == "-" else split_list(raw)

    profile.skills = lst("Tecnologías/skills detectadas (agregá o quitá; '-' borra todo)", profile.skills)
    profile.primary_stack = [s for s in lst("Stack principal (las que más pesan en el ranking)",
                                            profile.primary_stack or profile.skills[:8])]
    for s in profile.primary_stack:
        if s not in profile.skills:
            profile.skills.append(s)
    while True:
        raw = ask("Años de experiencia profesional", "%g" % (profile.years_experience or 0))
        try:
            profile.years_experience = max(0.0, float(raw.replace(",", ".")))
            break
        except ValueError:
            print("  Ingresá un número, ej. 4.5")
    profile.seniority_level = "junior" if profile.years_experience < 2 else "mid" if profile.years_experience < 5 else "senior"
    if profile.suggested_terms:
        print("Otros términos frecuentes en tu CV que no conozco: %s" % ", ".join(profile.suggested_terms))
        extra = split_list(ask("¿Sumás alguno a tus skills? (copialos separados por coma; Enter = ninguno)", ""))
        for term in extra:
            if term not in profile.skills:
                profile.skills.append(term)
        profile.suggested_terms = []
    profile.roles_suited = lst("Puestos que te representan (en inglés, sin seniority)", profile.roles_suited)
    known = areas_mod.load_areas()
    chosen = [a for a in split_list(ask("Áreas de tu perfil (%s)" % ", ".join(known), ", ".join(profile.areas)).lower())
              if a in known]
    profile.areas = chosen or profile.areas
    return profile  # el país se pregunta una sola vez, en el asistente de preferencias
