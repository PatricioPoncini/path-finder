"""Modelos de datos compartidos por todo el pipeline."""
from __future__ import annotations

import hashlib
import html
import json
import re
from dataclasses import asdict, dataclass, field, fields
from typing import Any, Dict, List, Optional

SENIORITY_LEVELS = ["junior", "mid", "senior", "lead"]


def html_to_text(raw: str) -> str:
    """Convierte HTML simple a texto plano legible (sin dependencias extra)."""
    if not raw:
        return ""
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", raw)
    text = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</h[1-6]>|</tr>", "\n", text)
    text = re.sub(r"(?i)<li[^>]*>", "\n- ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text).replace("\xa0", " ")
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    return "\n".join(line.strip() for line in text.split("\n")).strip()


def stable_hash(obj: Any) -> str:
    data = json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()[:16]


@dataclass
class Job:
    id: str  # "<fuente>:<id-en-la-fuente>"
    source: str
    title: str
    company: str
    url: str
    location: str = ""
    # Restricciones geográficas explícitas de la fuente (vacío = sin restricción declarada)
    location_restrictions: List[str] = field(default_factory=list)
    remote: Optional[bool] = None  # None = desconocido
    description: str = ""
    tags: List[str] = field(default_factory=list)
    posted_at: str = ""  # ISO 8601 UTC
    salary: str = ""
    language: str = ""  # idioma declarado por la fuente (es, en...), si lo da

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Job":
        names = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in names})


@dataclass
class Match:
    job_id: str
    score: int  # 0-100
    eligible: str = "unclear"  # yes | no | unclear (¿puede aplicar desde su país?)
    seniority_fit: str = "unclear"  # below | good | above | unclear
    summary: str = ""
    reasons: List[str] = field(default_factory=list)
    gaps: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Match":
        names = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in names})


@dataclass
class Profile:
    """Perfil extraído del CV. Se guarda en data/profile.json (editable)."""

    name: str = ""
    headline: str = ""
    country: str = ""
    location: str = ""
    years_experience: float = 0
    seniority_level: str = "mid"
    summary: str = ""
    skills: List[str] = field(default_factory=list)
    primary_stack: List[str] = field(default_factory=list)
    domains: List[str] = field(default_factory=list)
    languages: List[Dict[str, str]] = field(default_factory=list)
    education: List[str] = field(default_factory=list)
    roles_suited: List[str] = field(default_factory=list)
    areas: List[str] = field(default_factory=list)  # áreas detectadas (tech, product, design, data...)
    suggested_terms: List[str] = field(default_factory=list)  # términos frecuentes del CV fuera del vocabulario
    linkedin_url: str = ""
    cv_hash: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Profile":
        names = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in names})


@dataclass
class Preferences:
    """Lo que la persona busca. Se guarda en data/preferences.yaml (editable a mano)."""

    target_roles: List[str] = field(default_factory=lambda: ["Software Engineer"])
    seniority: List[str] = field(default_factory=lambda: ["mid", "senior"])
    work_modes: List[str] = field(default_factory=lambda: ["remote"])  # remote | hybrid | onsite
    candidate_country: str = ""
    # Textos que, si aparecen en la restricción geográfica de una oferta, la hacen elegible
    eligible_regions: List[str] = field(
        default_factory=lambda: ["worldwide", "anywhere", "global", "remote"]
    )
    strict_region_filter: bool = True
    # Idiomas aceptados en la descripción de la oferta (códigos: es, en, pt, it, de, fr). Vacío = cualquiera
    job_languages: List[str] = field(default_factory=list)
    areas: List[str] = field(default_factory=list)  # vacío = las del perfil (o tech)
    must_have: List[str] = field(default_factory=list)  # imprescindibles: términos que la oferta debería mencionar
    preferred_stack: List[str] = field(default_factory=list)
    avoid_stack: List[str] = field(default_factory=list)
    exclude_keywords: List[str] = field(default_factory=list)  # en título/tags
    title_keywords: List[str] = field(default_factory=list)  # frases extra aceptadas en el título
    search_queries: List[str] = field(default_factory=list)  # si vacío se derivan de target_roles
    min_salary_usd: int = 0
    max_age_days: int = 30
    min_score: int = 40
    sources: List[str] = field(
        default_factory=lambda: ["remotive", "remoteok", "himalayas", "weworkremotely", "arbeitnow", "getonbrd"]
    )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Preferences":
        names = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in (data or {}).items() if k in names and v is not None})
