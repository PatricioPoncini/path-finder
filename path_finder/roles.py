"""Niveles de seniority, roles comunes (PM, PO, TL, Sr Software Engineer...) y su resolución."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

from . import areas as areas_mod

LEVELS = ["junior", "mid", "senior", "lead", "expert", "head"]
LEVEL_INDEX = {name: i for i, name in enumerate(LEVELS)}

# Se evalúan de mayor a menor nivel: "Senior Staff Engineer" es expert; "Senior Engineering Manager" es lead.
# "manager" suelto NO es nivel ("Product Manager" es un rol); solo lo es en compuestos de gestión de equipos.
_LEVEL_PATTERNS = [
    ("head", r"\b(head of|director|vp|vice president|chief|cto|cpo|cdo)\b|\bdirector(a)?\b"),
    ("expert", r"\b(staff|principal|expert|experto|experta|specialist|especialista|architect|arquitecto|distinguished|fellow)\b"),
    ("lead", r"\b(lead|tl|team lead|tech lead|l[ií]der|group|engineering manager|people manager|manager of|design manager|data manager)\b"),
    ("mid", r"\b(mid|mid[- ]level|middle|semi[- ]?senior|ssr|intermediate|semi sr\.?)(?!\w)"),
    ("senior", r"\b(senior|sr\.?|s[eé]nior)(?!\w)"),
    ("junior", r"\b(junior|jr\.?|intern(ship)?|trainee|entry[- ]level|graduate|apprentice|becario)(?!\w)"),
]
_LEVEL_RES = [(lvl, re.compile(p, re.I)) for lvl, p in _LEVEL_PATTERNS]

LEVEL_ALIASES = {
    "jr": "junior", "junior": "junior", "trainee": "junior",
    "ssr": "mid", "semi": "mid", "semi-senior": "mid", "semisenior": "mid", "semi senior": "mid", "mid": "mid",
    "middle": "mid", "mid-level": "mid",
    "sr": "senior", "sr.": "senior", "senior": "senior", "sénior": "senior",
    "lead": "lead", "tl": "lead", "tech lead": "lead", "team lead": "lead", "líder": "lead", "lider": "lead", "group": "lead",
    "expert": "expert", "experto": "expert", "staff": "expert", "principal": "expert", "specialist": "expert",
    "head": "head", "director": "head", "vp": "head",
}


def title_level(title: str) -> str:
    """Nivel que declara un título de oferta ('' si no dice)."""
    for level, rx in _LEVEL_RES:
        if rx.search(title):
            return level
    return ""


def normalize_levels(values: Iterable[str]) -> List[str]:
    out: List[str] = []
    for v in values:
        level = LEVEL_ALIASES.get(v.strip().lower())
        if level and level not in out:
            out.append(level)
    return sorted(out, key=lambda x: LEVEL_INDEX[x])


def level_fit(level: str, wanted: Iterable[str]) -> Tuple[str, int]:
    """(good|below|above, escalones fuera del rango buscado) para un nivel de título."""
    idx = [LEVEL_INDEX[w] for w in wanted if w in LEVEL_INDEX]
    if not level or not idx:
        return "unclear", 0
    i = LEVEL_INDEX[level]
    if i < min(idx):
        return "below", min(idx) - i
    if i > max(idx):
        return "above", i - max(idx)
    return "good", 0


# --- catálogo de roles (desde los paquetes de área) --------------------------------------------
def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower().replace("-", " ").replace(".", ""))


def catalog() -> Dict[str, Tuple[str, str]]:
    """texto normalizado (título o alias) -> (título canónico, id de área)."""
    out: Dict[str, Tuple[str, str]] = {}
    for area in areas_mod.load_areas().values():
        for role in area.roles:
            for name in [role.title] + role.aliases:
                out.setdefault(_norm(name), (role.title, area.id))
    return out


def role_def(title: str):
    """RoleDef del catálogo para un título canónico (o None)."""
    for area in areas_mod.load_areas().values():
        for role in area.roles:
            if role.title.lower() == title.lower():
                return role
    return None


def role_names(text: str) -> List[str]:
    """Todas las formas aceptadas en un título para el rol `text` (título + alias del catálogo).

    Si `text` no está en el catálogo (o no tiene aliases), devuelve [text]."""
    hit = catalog().get(_norm(text))
    if hit:
        role = role_def(hit[0])
        if role:
            return [role.title] + role.aliases
    return [text]


@dataclass
class Resolved:
    title: str          # lo que se busca ("Product Manager")
    level: str = ""     # nivel implícito ("senior" para "Sr PM")
    area: str = ""      # área del catálogo ("" si no se reconoció)
    known: bool = False


@dataclass
class Preset:
    label: str
    title: str
    level: str
    area: str
    aliases: Tuple[str, ...] = ()


PRESETS: List[Preset] = [
    Preset("Software Engineer", "Software Engineer", "", "tech", ("swe", "software developer", "developer", "desarrollador")),
    Preset("Sr Software Engineer", "Software Engineer", "senior", "tech", ("senior software engineer", "sr developer", "senior developer", "sr swe")),
    Preset("Backend Engineer", "Backend Engineer", "", "tech", ("backend developer", "backend")),
    Preset("Sr Backend Engineer", "Backend Engineer", "senior", "tech", ("senior backend engineer", "sr backend")),
    Preset("Frontend Engineer", "Frontend Engineer", "", "tech", ("frontend developer", "frontend")),
    Preset("Full Stack Engineer", "Full Stack Engineer", "", "tech", ("fullstack", "full stack developer", "fullstack developer")),
    Preset("TL (Tech Lead)", "Tech Lead", "lead", "tech", ("tl", "tech lead", "technical lead", "team lead")),
    Preset("Expert / Staff Engineer", "Software Engineer", "expert", "tech",
           ("expert", "staff engineer", "principal engineer", "expert engineer", "staff", "principal")),
    Preset("DevOps / SRE", "DevOps Engineer", "", "tech", ("devops", "sre")),
    Preset("PM (Product Manager)", "Product Manager", "", "product", ("pm", "product manager")),
    Preset("Sr PM", "Product Manager", "senior", "product", ("sr pm", "senior pm", "senior product manager", "sr product manager")),
    Preset("Group PM", "Product Manager", "lead", "product", ("group pm", "gpm", "group product manager")),
    Preset("PO (Product Owner)", "Product Owner", "", "product", ("po", "product owner")),
    Preset("Sr PO", "Product Owner", "senior", "product", ("sr po", "senior po", "senior product owner")),
    Preset("Head of Product", "Head of Product", "head", "product", ("cpo", "director of product", "vp product")),
    Preset("UX/UI Designer", "UX/UI Designer", "", "design", ("ux designer", "ui designer", "ux/ui", "designer")),
    Preset("Sr Product Designer", "Product Designer", "senior", "design", ("senior product designer", "sr designer", "senior designer")),
    Preset("Data Analyst", "Data Analyst", "", "data", ("analyst",)),
    Preset("Data Scientist", "Data Scientist", "", "data", ()),
    Preset("Sr Data Scientist", "Data Scientist", "senior", "data", ("senior data scientist",)),
    Preset("Data Engineer", "Data Engineer", "", "data", ()),
    Preset("ML Engineer", "Machine Learning Engineer", "", "data", ("machine learning engineer", "mle", "mlops")),
]


def _preset_index() -> Dict[str, Preset]:
    idx: Dict[str, Preset] = {}
    for p in PRESETS:
        for name in (p.label, p.title if not p.level else "", *p.aliases):
            if name:
                idx.setdefault(_norm(re.sub(r"\(.*?\)", "", name)), p)
    return idx


def resolve_role(text: str) -> Resolved:
    """'Sr PM' -> Product Manager/senior; 'TL' -> Tech Lead/lead; 'Data Analyst' -> Data Analyst; libre -> tal cual."""
    raw = text.strip()
    key = _norm(raw)
    preset = _preset_index().get(key)
    if preset:
        return Resolved(preset.title, preset.level, preset.area, True)
    hit = catalog().get(key)
    if hit:
        return Resolved(hit[0], "", hit[1], True)
    words = key.split()
    for n in (2, 1):  # "semi senior pm", "sr pm", "senior data analyst"
        if len(words) > n:
            level = LEVEL_ALIASES.get(" ".join(words[:n]))
            if level:
                rest = " ".join(words[n:])
                inner = _preset_index().get(rest) or None
                hit = catalog().get(rest)
                if inner:
                    return Resolved(inner.title, level, inner.area, True)
                if hit:
                    return Resolved(hit[0], level, hit[1], True)
                return Resolved(" ".join(raw.split()[n:]), level, "", False)
    return Resolved(raw, "", "", False)


def resolve_roles(values: Iterable[str]) -> Tuple[List[str], List[str], List[str]]:
    """(títulos únicos, niveles explícitos, áreas) para una lista como ['Sr PM', 'PO']."""
    titles: List[str] = []
    levels: List[str] = []
    areas: List[str] = []
    for v in values:
        if not v.strip():
            continue
        r = resolve_role(v)
        if r.title and r.title.lower() not in [t.lower() for t in titles]:
            titles.append(r.title)
        if r.level and r.level not in levels:
            levels.append(r.level)
        if r.area and r.area not in areas:
            areas.append(r.area)
    return titles, sorted(levels, key=lambda x: LEVEL_INDEX[x]), areas
