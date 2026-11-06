"""Extracción del perfil a partir del CV (PDF/txt/md) con reglas, sin IA.

Es una aproximación: detecta tecnologías contra un vocabulario, estima los años de experiencia
por rangos de fechas y sugiere puestos por títulos conocidos. `path-finder init` muestra el resultado
y deja corregirlo.
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from . import areas as areas_mod
from . import config
from .config import SetupError
from .countries import COUNTRIES, COUNTRY_CANONICAL
from .models import Profile, stable_hash

MIN_PDF_TEXT_CHARS = 50
PRIMARY_STACK_SIZE = 8

MONTHS = {
    "jan": 1, "ene": 1, "feb": 2, "mar": 3, "apr": 4, "abr": 4, "may": 5, "jun": 6, "jul": 7,
    "aug": 8, "ago": 8, "sep": 9, "set": 9, "oct": 10, "nov": 11, "dec": 12, "dic": 12,
}
PRESENT = r"(?:present|presente|actualidad|actual|current|currently|hoy|now|ahora|date)"
_MONTH = r"(?:(?P<%s_m>[A-Za-z]{3,10})\.?,?\s+)?"
_NUM_MONTH = r"(?:(?P<%s_n>\d{1,2})/)?"
DATE_RANGE_RE = re.compile(
    r"(?<![\d/])" + _NUM_MONTH % "s" + _MONTH % "s" + r"(?P<s_y>(?:19|20)\d{2})"
    r"\s*(?:-|–|—|to|a|hasta|until)\s*"
    r"(?:" + _NUM_MONTH % "e" + _MONTH % "e" + r"(?P<e_y>(?:19|20)\d{2})|(?P<now>" + PRESENT + r"))(?!\d)",
    re.I,
)
EDU_RE = re.compile(
    r"universidad|university|college|licenciatura|ingenier[ií]a en|bachelor|master|m[aá]ster|tecnicatura|"
    r"carrera|degree|grado|instituto|escuela|school|bootcamp|curso|course|certificat|educaci[oó]n|education|"
    r"formaci[oó]n|estudios|secundari|bachiller", re.I)
EXP_HEADING_RE = re.compile(
    r"experien|experience|employment|work history|trayectoria|historial laboral|empleo|career", re.I)


def read_cv(path: Path) -> str:
    """Texto del CV. PDF (texto seleccionable), .txt o .md."""
    path = Path(path).expanduser()
    if not path.is_file():
        raise SetupError("No encuentro el CV en: %s" % path)
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        text = "\n".join((page.extract_text() or "") for page in reader.pages).strip()
        if len(text) < MIN_PDF_TEXT_CHARS:
            raise SetupError(
                "No pude leer texto del PDF (¿está escaneado como imagen?). Exportalo con texto seleccionable "
                "o pasá el CV como .txt/.md.")
        return text
    if suffix in (".txt", ".md", ".markdown"):
        return path.read_text(encoding="utf-8", errors="replace")
    raise SetupError("Formato no soportado (%s). Usá PDF, .txt o .md." % suffix)


# --- tecnologías --------------------------------------------------------------------------------
def _alias_pattern(alias: str, ambiguous: Set[str]) -> "re.Pattern[str]":
    flags = 0 if (len(alias) <= 3 or alias in ambiguous) else re.I
    return re.compile(r"(?<![A-Za-z0-9_+#])%s(?![A-Za-z0-9_+#])" % re.escape(alias), flags)


_PATTERNS: Dict[str, Dict[str, List["re.Pattern[str]"]]] = {}


def _patterns() -> Dict[str, List["re.Pattern[str]"]]:
    skills, _concepts, ambiguous = areas_mod.vocabulary()
    key = str(config.home_dir() / "areas")
    if key not in _PATTERNS:
        _PATTERNS.clear()
        _PATTERNS[key] = {name: [_alias_pattern(a, ambiguous) for a in [name] + aliases]
                          for name, aliases in skills.items()}
    return _PATTERNS[key]


def detect_skills(text: str) -> List[str]:
    """Skills del vocabulario (todas las áreas) presentes en el texto, de más a menos mencionadas."""
    found: List[Tuple[int, int, str]] = []
    for name, pats in _patterns().items():
        count, first = 0, len(text)
        for pat in pats:
            for m in pat.finditer(text):
                count += 1
                first = min(first, m.start())
        if count:
            found.append((-count, first, name))
    return [name for _, _, name in sorted(found)]


# --- experiencia --------------------------------------------------------------------------------
def _month(name: Optional[str], num: Optional[str], default: int) -> int:
    if num and 1 <= int(num) <= 12:
        return int(num)
    if name and name[:3].lower() in MONTHS:
        return MONTHS[name[:3].lower()]
    return default


def experience_months(text: str, today: Optional[date] = None) -> int:
    """Meses de experiencia: une los rangos de fechas de la sección de experiencia (sin solapar)."""
    today = today or date.today()
    intervals: List[Tuple[int, int]] = []
    in_education = False
    for line in text.splitlines():
        stripped = line.strip()
        if 0 < len(stripped) < 40:
            if EDU_RE.search(stripped):
                in_education = True
            elif EXP_HEADING_RE.search(stripped):
                in_education = False
        if in_education or EDU_RE.search(stripped):
            continue
        for m in DATE_RANGE_RE.finditer(stripped):
            start = int(m.group("s_y")) * 12 + _month(m.group("s_m"), m.group("s_n"), 1) - 1
            if m.group("now"):
                end = today.year * 12 + today.month - 1
            else:
                end = int(m.group("e_y")) * 12 + _month(m.group("e_m"), m.group("e_n"), 12) - 1
            end = min(end, today.year * 12 + today.month - 1)
            if end > start:
                intervals.append((start, end))
    total, cur_start, cur_end = 0, None, None
    for s, e in sorted(intervals):
        if cur_end is None or s > cur_end:
            if cur_end is not None:
                total += cur_end - cur_start
            cur_start, cur_end = s, e
        else:
            cur_end = max(cur_end, e)
    if cur_end is not None:
        total += cur_end - cur_start
    return total


def seniority_from_years(years: float) -> str:
    return "junior" if years < 2 else "mid" if years < 5 else "senior"


# --- puestos, áreas, nombre, país ---------------------------------------------------------------
def _role_counts(text: str, areas: List["areas_mod.Area"]) -> List[Tuple[int, str, str]]:
    found: List[Tuple[int, str, str]] = []
    for area in areas:
        for role in area.roles:
            n = sum(len(re.findall(p, text, re.I)) for p in role.patterns)
            if n:
                found.append((-n, role.title, area.id))
    return sorted(found)


def detect_roles(text: str, limit: int = 3) -> List[str]:
    titles: List[str] = []
    for _, title, _area in _role_counts(text, list(areas_mod.load_areas().values())):
        if title not in titles:
            titles.append(title)
    return titles[:limit]


def detect_areas(text: str, skills: List[str], max_areas: int = 2) -> List[str]:
    """Áreas dominantes: roles (peso 3) + skills propias del área (sin conceptos genéricos)."""
    all_areas = areas_mod.load_areas()
    scores: Dict[str, int] = {a: 0 for a in all_areas}
    for n, _title, area_id in _role_counts(text, list(all_areas.values())):
        scores[area_id] += 3 * -n
    for area_id, area in all_areas.items():
        scores[area_id] += sum(1 for sk in skills if sk in area.skills and sk not in area.concepts)
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    top = ranked[0][1]
    if top < 3:
        return []
    return [a for a, sc in ranked[:max_areas] if sc >= max(3, 0.4 * top)]


_STOP_CAPS = set("""
the and for with from this that our your you are will have has but not all any can who what when where why how
una uno los las del con por para que como pero sus nos más muy sin sobre desde hasta entre durante
enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre
january february march april june july august september october november december
lunes martes miércoles jueves viernes sábado domingo monday tuesday wednesday thursday friday saturday sunday
presente actualidad present current experiencia experience educación education skills habilidades idiomas languages
español inglés english spanish ingeniería sistemas universidad university licenciatura gestión desarrollo proyecto proyectos
""".split())
_ACRONYM = re.compile(r"(?<![A-Za-z0-9])[A-Z][A-Z0-9&/]{1,5}(?![A-Za-z0-9])")
_MIDWORD = re.compile(r"(?<=[a-záéíóú,;(] )[A-Z][A-Za-z0-9]{3,}(?![A-Za-z0-9])")


def suggest_terms(text: str, known: List[str], limit: int = 12) -> List[str]:
    """Siglas y nombres propios frecuentes del CV que no están en el vocabulario (se proponen, no se agregan solos)."""
    skills, _c, _a = areas_mod.vocabulary()
    known_l = {k.lower() for k in known} | {k.lower() for k in skills} | {a.lower() for al in skills.values() for a in al}
    counts: Dict[str, int] = {}
    for rx in (_ACRONYM, _MIDWORD):
        for m in rx.finditer(text):
            term = m.group(0)
            low = term.lower()
            if low in known_l or low in _STOP_CAPS or term.isdigit() or re.fullmatch(r"(19|20)\d\d", term):
                continue
            counts[term] = counts.get(term, 0) + 1
    ranked = sorted((t for t, n in counts.items() if n >= 2), key=lambda t: (-counts[t], t))
    return ranked[:limit]


def detect_name(text: str) -> str:
    for line in text.splitlines()[:8]:
        line = line.strip()
        words = line.split()
        if 2 <= len(words) <= 5 and not re.search(r"[\d@/:|]", line) and all(w[0].isalpha() for w in words):
            if not re.search(r"curriculum|resume|\bcv\b|developer|engineer|desarrollador", line, re.I):
                return line.title() if line.isupper() else line
    return ""


def detect_country(text: str) -> str:
    head = text[:1200]
    best: Optional[Tuple[int, str]] = None
    for country in COUNTRIES:
        m = re.search(r"(?<!\w)%s(?!\w)" % re.escape(country), head)
        if m and (best is None or m.start() < best[0]):
            best = (m.start(), country)
    return COUNTRY_CANONICAL.get(best[1], best[1]) if best else ""


# --- entrada principal --------------------------------------------------------------------------
def extract_profile(
    cv_path: Path,
    linkedin_url: str = "",
    extra_text_path: Optional[Path] = None,
    today: Optional[date] = None,
) -> Profile:
    text = read_cv(cv_path)
    extra = read_cv(extra_text_path) if extra_text_path else ""
    full = text + "\n" + extra
    skills = detect_skills(full)
    area_ids = detect_areas(full, skills)
    dominant = areas_mod.resolve(area_ids)
    months = experience_months(text, today)
    years = round(months / 12.0, 1)
    roles = detect_roles(full)
    if not roles and skills:
        roles = [dominant[0].roles[0].title]
    own = [s for s in skills if any(s in a.skills for a in dominant)]
    concepts = areas_mod.merged_set(dominant, "concepts")
    primary = [s for s in own if s not in concepts][:PRIMARY_STACK_SIZE]
    return Profile(
        name=detect_name(text),
        headline=roles[0] if roles else "",
        country=detect_country(text),
        years_experience=years,
        seniority_level=seniority_from_years(years),
        skills=skills,
        primary_stack=primary,
        roles_suited=roles,
        areas=area_ids,
        suggested_terms=suggest_terms(full, skills),
        linkedin_url=linkedin_url,
        cv_hash=stable_hash([text, extra]),
    )
