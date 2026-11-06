"""Interfaz común de las fuentes de ofertas y utilidades compartidas."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, List, Optional, Tuple

import httpx

from ..models import Job, Preferences

USER_AGENT = "jobbot/0.1 (personal job search tool)"
TIMEOUT = 25.0

SENIORITY_WORDS = {
    "junior", "jr", "semi", "semisenior", "semi-senior", "ssr", "mid", "mid-level", "middle",
    "senior", "sr", "lead", "staff", "principal", "intern", "trainee", "expert", "specialist", "tl",
}


def make_client() -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": USER_AGENT, "Accept": "application/json, application/xml, */*"},
        timeout=TIMEOUT,
        follow_redirects=True,
    )


def iso_from_epoch(value: Any) -> str:
    try:
        return datetime.fromtimestamp(int(float(value)), tz=timezone.utc).isoformat(timespec="seconds")
    except (TypeError, ValueError, OverflowError, OSError):
        return ""


def search_queries(prefs: Preferences, limit: int = 3) -> List[str]:
    """Consultas de búsqueda: las del usuario o los roles objetivo sin palabras de seniority."""
    if prefs.search_queries:
        return prefs.search_queries[:limit]
    from ..roles import catalog

    out: List[str] = []
    for role in prefs.target_roles:
        hit = catalog().get(re.sub(r"\s+", " ", role.strip().lower().replace("-", " ").replace(".", "")))
        if hit:  # "Tech Lead", "Head of Product": el nivel es parte del nombre del rol
            q = hit[0]
        else:
            words = [w for w in re.split(r"\s+", role.strip()) if w.lower() not in SENIORITY_WORDS]
            q = " ".join(words).strip()
        if q and q.lower() not in [o.lower() for o in out]:
            out.append(q)
    return out[:limit] or ["software engineer"]


class Source:
    """Una fuente devuelve ofertas normalizadas. Las excepciones las captura el runner."""

    name = ""
    label = ""  # nombre a mostrar/atribuir en el reporte
    homepage = ""
    requires_key = False
    # Si el usuario acepta alguno de estos idiomas, la fuente se activa sola aunque no esté en `sources`
    auto_languages: Tuple[str, ...] = ()

    def available(self) -> Optional[str]:
        """None si se puede usar; si no, el motivo (ej. falta una clave)."""
        return None

    def fetch(self, prefs: Preferences, client: httpx.Client) -> List[Job]:
        raise NotImplementedError
