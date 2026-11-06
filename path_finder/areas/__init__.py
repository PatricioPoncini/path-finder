"""Paquetes de área: vocabulario de skills, catálogo de roles, fuentes y pesos por profesión.

Cada área es un YAML (`path_finder/areas/*.yaml`). El usuario puede sumar o pisar áreas con `data/areas/*.yaml`
sin tocar código. Ver README ("Áreas").
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set

import yaml

from .. import config
from ..config import SetupError

BUILTIN_DIR = Path(__file__).parent
DEFAULT_AREA = "tech"
DEFAULT_WEIGHTS = {"primary": 9, "other": 3, "preferred": 4, "title": 10, "seniority": 8}
REQUIRED_KEYS = ("id", "label", "skills", "roles")


@dataclass
class RoleDef:
    title: str
    aliases: List[str] = field(default_factory=list)
    patterns: List[str] = field(default_factory=list)  # regex, sin distinguir mayúsculas


@dataclass
class Area:
    id: str
    label: str
    skills: Dict[str, List[str]]
    roles: List[RoleDef]
    concepts: Set[str] = field(default_factory=set)
    ambiguous: Set[str] = field(default_factory=set)
    title_nouns: List[str] = field(default_factory=list)
    feeds: Dict[str, List[str]] = field(default_factory=dict)
    weights: Dict[str, int] = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))


def _parse(raw: dict, source: str) -> Area:
    if not isinstance(raw, dict):
        raise SetupError("Área inválida en %s: se esperaba un mapa YAML" % source)
    missing = [k for k in REQUIRED_KEYS if not raw.get(k)]
    if missing:
        raise SetupError("Área inválida en %s: faltan %s" % (source, ", ".join(missing)))
    skills = {str(k): [str(a) for a in (v or [])] for k, v in raw["skills"].items()}
    roles = []
    for r in raw["roles"]:
        if not isinstance(r, dict) or not r.get("title"):
            raise SetupError("Área %s (%s): cada rol necesita `title`" % (raw["id"], source))
        roles.append(RoleDef(str(r["title"]), [str(a) for a in r.get("aliases") or []],
                             [str(p) for p in r.get("patterns") or []]))
    weights = dict(DEFAULT_WEIGHTS)
    weights.update({k: int(v) for k, v in (raw.get("weights") or {}).items() if k in DEFAULT_WEIGHTS})
    return Area(
        id=str(raw["id"]), label=str(raw["label"]), skills=skills, roles=roles,
        concepts=set(raw.get("concepts") or []), ambiguous=set(raw.get("ambiguous") or []),
        title_nouns=[str(n).lower() for n in raw.get("title_nouns") or []],
        feeds={k: [str(x) for x in (v or [])] for k, v in (raw.get("feeds") or {}).items()},
        weights=weights,
    )


def _load_dir(path: Path) -> Dict[str, Area]:
    out: Dict[str, Area] = {}
    if path.is_dir():
        for f in sorted(path.glob("*.yaml")):
            try:
                raw = yaml.safe_load(f.read_text(encoding="utf-8"))
            except yaml.YAMLError as e:
                raise SetupError("No pude leer el área %s: %s" % (f, e))
            area = _parse(raw, str(f))
            out[area.id] = area
    return out


_CACHE: Dict[str, Dict[str, Area]] = {}


def load_areas() -> Dict[str, Area]:
    """Áreas incluidas + las del usuario (`data/areas/`), que suman o pisan por id."""
    user_dir = config.home_dir() / "areas"
    key = str(user_dir)
    if key not in _CACHE:
        areas = _load_dir(BUILTIN_DIR)
        areas.update(_load_dir(user_dir))
        _CACHE[key] = areas
    return _CACHE[key]


_VOCAB: Dict[str, tuple] = {}


def vocabulary():
    """(skills, concepts, ambiguous) de TODAS las áreas cargadas, para detectar y comparar términos."""
    key = str(config.home_dir() / "areas")
    load_areas()
    if key not in _VOCAB:
        every = list(load_areas().values())
        _VOCAB[key] = (merged_skills(every), merged_set(every, "concepts"), merged_set(every, "ambiguous"))
    return _VOCAB[key]


def clear_cache() -> None:
    _CACHE.clear()
    _VOCAB.clear()


def resolve(ids: Optional[Iterable[str]]) -> List[Area]:
    """Áreas por id (ignora desconocidas); sin ids, el área por defecto (tech)."""
    areas = load_areas()
    chosen = [areas[i] for i in (ids or []) if i in areas]
    return chosen or [areas[DEFAULT_AREA]]


def merged_skills(areas: Iterable[Area]) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {}
    for a in areas:
        for name, aliases in a.skills.items():
            merged = out.setdefault(name, [])
            merged.extend(x for x in aliases if x not in merged)
    return out


def merged_set(areas: Iterable[Area], attr: str) -> Set[str]:
    out: Set[str] = set()
    for a in areas:
        out |= getattr(a, attr)
    return out
