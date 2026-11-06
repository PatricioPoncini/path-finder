"""Detección del idioma de una oferta sin dependencias: conteo de palabras funcionales frecuentes."""
from __future__ import annotations

import re
from typing import Dict, List, Set

LANGUAGE_NAMES = {
    "es": "español", "en": "inglés", "pt": "portugués", "it": "italiano", "de": "alemán", "fr": "francés",
}
ALIASES = {
    "es": "es", "spanish": "es", "español": "es", "espanol": "es", "castellano": "es",
    "en": "en", "english": "en", "ingles": "en", "inglés": "en",
    "pt": "pt", "portuguese": "pt", "portugués": "pt", "portugues": "pt",
    "it": "it", "italian": "it", "italiano": "it",
    "de": "de", "german": "de", "alemán": "de", "aleman": "de", "deutsch": "de",
    "fr": "fr", "french": "fr", "francés": "fr", "frances": "fr", "français": "fr",
}

_STOPWORDS: Dict[str, Set[str]] = {
    "es": set("de la el en y los las del con para por una un que se su al es lo como más experiencia equipo "
              "trabajo empresa desarrollo conocimientos requisitos buscamos años sobre nuestro nuestra ser "
              "tener también están tu te sus nuevo nueva".split()),
    "en": set("the and of to in for with a an is are will our you your we as on be or at this that have "
              "experience team work skills requirements years about from has who their can".split()),
    "pt": set("de da do em e os as dos das com para por uma um que se sua ao é como mais experiência equipe "
              "trabalho empresa desenvolvimento conhecimentos requisitos anos sobre nosso nossa ser ter você "
              "não também".split()),
    "it": set("di il la le lo gli dei del della delle con per una un che si su al è come più esperienza "
              "team lavoro azienda sviluppo conoscenza requisiti anni sulla nostro nostra essere hai sei "
              "non anche nel nella".split()),
    "de": set("der die das und den von zu mit für ein eine ist sind wir sie ihr auf im dem des nicht auch "
              "bei als oder erfahrung team arbeit unternehmen entwicklung kenntnisse anforderungen jahre "
              "über unser unsere werden haben".split()),
    "fr": set("le la les des du de et en un une pour avec que qui est sont nous vous votre notre dans sur "
              "au aux par pas plus expérience équipe travail entreprise développement connaissances "
              "années être avoir".split()),
}
_WORD = re.compile(r"[a-záéíóúüñàèìòùâêîôûçãõäößœ']+", re.I)
MIN_WORDS = 25      # menos que esto: no se arriesga un veredicto
MIN_LEAD = 1.6      # el ganador debe superar al segundo por esta proporción (es/pt/fr comparten palabras)


def normalize_languages(values: List[str]) -> List[str]:
    """['Español', 'english', 'xx'] -> ['es', 'en'] (descarta lo que no reconoce)."""
    out: List[str] = []
    for v in values:
        code = ALIASES.get(v.strip().lower())
        if code and code not in out:
            out.append(code)
    return out


def detect_language(text: str) -> str:
    """Código ISO del idioma dominante ('es', 'en', ...) o '' si no hay evidencia suficiente."""
    words = [w.lower() for w in _WORD.findall(text or "")]
    if len(words) < MIN_WORDS:
        return ""
    scores = {lang: sum(1 for w in words if w in stop) for lang, stop in _STOPWORDS.items()}
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    (best, top), (_, second) = ranked[0], ranked[1]
    return best if top >= 6 and top >= MIN_LEAD * second else ""
