"""Extracción del perfil estructurado a partir del CV (PDF/txt/md) usando Claude."""
from __future__ import annotations

import base64
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .claude import Claude
from .config import SetupError
from .models import Profile, stable_hash

MIN_PDF_TEXT_CHARS = 200

PROFILE_TOOL: Dict[str, Any] = {
    "name": "save_profile",
    "description": "Guarda el perfil profesional extraído del CV.",
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "headline": {"type": "string", "description": "Título profesional corto, ej. 'Backend Engineer'"},
            "country": {"type": "string", "description": "País de residencia actual (nombre completo en inglés)"},
            "location": {"type": "string", "description": "Ciudad/región, si figura"},
            "years_experience": {"type": "number", "description": "Años de experiencia profesional total"},
            "seniority_level": {"type": "string", "enum": ["junior", "mid", "senior", "lead"]},
            "summary": {"type": "string", "description": "Resumen de 2-3 oraciones, fiel al CV"},
            "skills": {"type": "array", "items": {"type": "string"}, "description": "Tecnologías y habilidades técnicas, nombres normalizados"},
            "primary_stack": {"type": "array", "items": {"type": "string"}, "description": "Las 5-8 tecnologías centrales"},
            "domains": {"type": "array", "items": {"type": "string"}, "description": "Áreas/industrias de experiencia"},
            "languages": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"language": {"type": "string"}, "level": {"type": "string"}},
                    "required": ["language", "level"],
                },
            },
            "education": {"type": "array", "items": {"type": "string"}},
            "roles_suited": {
                "type": "array",
                "items": {"type": "string"},
                "description": "3-5 títulos de puesto en inglés con los que buscar ofertas (sin seniority), ej. 'Backend Engineer'",
            },
        },
        "required": [
            "name", "headline", "country", "years_experience", "seniority_level",
            "summary", "skills", "primary_stack", "roles_suited",
        ],
    },
}

SYSTEM = (
    "Sos un reclutador técnico. Extraés un perfil estructurado a partir de un CV. "
    "Usá SOLO información presente en el texto; no inventes. Si un dato no figura, dejalo vacío. "
    "Estimá los años de experiencia sumando la experiencia profesional (no la académica). "
    "seniority_level: junior (<2 años), mid (2-4), senior (5+ o liderazgo técnico claro), lead (gestión/arquitectura de equipos)."
)


def read_cv(path: Path) -> Tuple[str, Optional[bytes]]:
    """Devuelve (texto, bytes_pdf_si_el_texto_no_alcanza)."""
    path = Path(path).expanduser()
    if not path.is_file():
        raise SetupError("No encuentro el CV en: %s" % path)
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        text = "\n".join((page.extract_text() or "") for page in reader.pages).strip()
        if len(text) < MIN_PDF_TEXT_CHARS:
            return text, path.read_bytes()  # probablemente escaneado: lo lee Claude directamente
        return text, None
    if suffix in (".txt", ".md", ".markdown"):
        return path.read_text(encoding="utf-8", errors="replace"), None
    raise SetupError("Formato no soportado (%s). Usá PDF, .txt o .md." % suffix)


def extract_profile(
    claude: Claude,
    cv_path: Path,
    linkedin_url: str = "",
    extra_text_path: Optional[Path] = None,
) -> Profile:
    text, pdf_bytes = read_cv(cv_path)
    extra = ""
    if extra_text_path:
        extra, _ = read_cv(extra_text_path)

    content: List[Dict[str, Any]] = []
    if pdf_bytes is not None:
        content.append({
            "type": "document",
            "source": {"type": "base64", "media_type": "application/pdf",
                       "data": base64.standard_b64encode(pdf_bytes).decode("ascii")},
        })
        content.append({"type": "text", "text": "Extraé el perfil de este CV."})
    else:
        content.append({"type": "text", "text": "CV:\n\n%s\n\nExtraé el perfil." % text})
    if extra:
        content.append({"type": "text", "text": "Información adicional del candidato (ej. LinkedIn):\n\n%s" % extra})

    data = claude.tool_call(SYSTEM, content, PROFILE_TOOL, max_tokens=2048)
    profile = Profile.from_dict(data)
    profile.linkedin_url = linkedin_url
    profile.cv_hash = stable_hash([text, extra, len(pdf_bytes or b"")])
    return profile
