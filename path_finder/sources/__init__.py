"""Registro de fuentes. Para agregar una: crear el módulo, heredar de `Source` y sumarla acá."""
from __future__ import annotations

from typing import Dict, List, Tuple

from ..models import Job, Preferences
from .arbeitnow import Arbeitnow
from .base import Source, make_client
from .getonbrd import GetOnBoard
from .himalayas import Himalayas
from .jobicy import Jobicy
from .remoteok import RemoteOK
from .remotive import Remotive
from .weworkremotely import WeWorkRemotely
from .workingnomads import WorkingNomads

SOURCES: Dict[str, Source] = {
    s.name: s for s in (Remotive(), RemoteOK(), Himalayas(), WeWorkRemotely(), Arbeitnow(), GetOnBoard(), Jobicy(),
                                WorkingNomads())
}


def active_sources(prefs: Preferences) -> List[str]:
    """Fuentes elegidas por el usuario + las que su idioma de ofertas activa solas (ej. español -> Get on Board)."""
    names = list(prefs.sources)
    for name, source in SOURCES.items():
        if name not in names and any(lang in prefs.job_languages for lang in source.auto_languages):
            names.append(name)
    return names


def fetch_all(prefs: Preferences, progress=None) -> Tuple[List[Job], Dict[str, str]]:
    """Trae ofertas de las fuentes activas. Devuelve (ofertas, {fuente: error/aviso}).

    Una fuente que falla no frena a las demás.
    """
    jobs: List[Job] = []
    problems: Dict[str, str] = {}
    with make_client() as client:
        for name in active_sources(prefs):
            source = SOURCES.get(name)
            if source is None:
                problems[name] = "fuente desconocida (válidas: %s)" % ", ".join(SOURCES)
                continue
            try:
                got = source.fetch(prefs, client)
            except Exception as e:  # noqa: BLE001 - aislar fallas de red/formato por fuente
                problems[name] = "error: %s" % e
                continue
            if progress:
                progress(name, len(got))
            jobs.extend(got)
    return jobs, problems
