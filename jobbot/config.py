"""Rutas, carga de .env y persistencia de perfil/preferencias."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

import yaml

from .models import Preferences, Profile

PREFS_HEADER = """\
# Preferencias de búsqueda de jobbot. Editá este archivo a mano o corré `jobbot init --prefs-only`.
# Qué significa cada campo: ver README.md (sección "Preferencias").
"""


class SetupError(RuntimeError):
    """Falta algo que el usuario debe configurar (mensaje pensado para mostrarse tal cual)."""


def home_dir() -> Path:
    return Path(os.environ.get("JOBBOT_HOME") or (Path.cwd() / "data")).expanduser()


def profile_path() -> Path:
    return home_dir() / "profile.json"


def prefs_path() -> Path:
    return home_dir() / "preferences.yaml"


def db_path() -> Path:
    return home_dir() / "jobs.db"


def reports_dir() -> Path:
    return home_dir() / "reports"


def load_env() -> None:
    """Carga variables de un .env (cwd) sin pisar las ya definidas en el entorno."""
    path = Path.cwd() / ".env"
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip("'\"")
        if key and value and key not in os.environ:
            os.environ[key] = value


def save_profile(profile: Profile) -> None:
    profile_path().parent.mkdir(parents=True, exist_ok=True)
    profile_path().write_text(
        json.dumps(profile.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def load_profile() -> Profile:
    if not profile_path().is_file():
        raise SetupError("No hay perfil todavía. Corré primero: jobbot init")
    return Profile.from_dict(json.loads(profile_path().read_text(encoding="utf-8")))


def save_prefs(prefs: Preferences) -> None:
    prefs_path().parent.mkdir(parents=True, exist_ok=True)
    body = yaml.safe_dump(prefs.to_dict(), sort_keys=False, allow_unicode=True, width=100)
    prefs_path().write_text(PREFS_HEADER + body, encoding="utf-8")


def load_prefs(model_override: Optional[str] = None) -> Preferences:
    if not prefs_path().is_file():
        raise SetupError("No hay preferencias todavía. Corré primero: jobbot init")
    prefs = Preferences.from_dict(yaml.safe_load(prefs_path().read_text(encoding="utf-8")) or {})
    env_model = os.environ.get("JOBBOT_MODEL")
    if model_override:
        prefs.model = model_override
    elif env_model:
        prefs.model = env_model
    return prefs
