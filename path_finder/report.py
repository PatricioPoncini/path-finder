"""Reportes Markdown y HTML con las ofertas ordenadas por score."""
from __future__ import annotations

import html
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .models import Job, Match, Preferences, Profile
from .sources import SOURCES

ELIGIBLE_LABEL = {"yes": "✅ Podés aplicar", "unclear": "❔ Elegibilidad no clara", "no": "⛔ No elegible"}
FIT_LABEL = {"below": "más junior de lo que buscás", "good": "seniority adecuado",
             "above": "pide más seniority", "unclear": "seniority no claro"}


FOOTER = ("Score calculado con reglas locales (sin IA) a partir de tu CV y tus preferencias: sirve para priorizar. "
          "Verificá siempre la elegibilidad regional antes de postular.")


@dataclass
class Entry:
    job: Job
    match: Match
    is_new: bool = False


def attribution(source: str) -> str:
    s = SOURCES.get(source)
    return "%s (%s)" % (s.label, s.homepage) if s else source


def build_entries(
    jobs: List[Job], matches: Dict[str, Match], new_ids: set, min_score: int,
    show_ineligible: bool = False, only_new: bool = False,
) -> List[Entry]:
    entries: List[Entry] = []
    for job in jobs:
        m = matches.get(job.id)
        if m is None or m.score < min_score:
            continue
        if m.eligible == "no" and not show_ineligible:
            continue
        if only_new and job.id not in new_ids:
            continue
        entries.append(Entry(job, m, job.id in new_ids))
    entries.sort(key=lambda e: (-e.match.score, e.job.title))
    return entries


def _header_lines(profile: Profile, prefs: Preferences, entries: List[Entry], stats: Dict[str, int]) -> List[str]:
    return [
        "Perfil: %s — %s" % (profile.name or "(sin nombre)", profile.headline),
        "Busca: %s | %s | áreas: %s | modalidad: %s | país: %s | idioma de la oferta: %s" % (
            ", ".join(prefs.target_roles), "/".join(prefs.seniority), ", ".join(prefs.areas or profile.areas) or "tech",
            ", ".join(prefs.work_modes), prefs.candidate_country or "n/a",
            ", ".join(prefs.job_languages) or "cualquiera"),
        "Ofertas en el reporte: %d (score mínimo %d). Analizadas: %d; descartadas por filtros: %d."
        % (len(entries), prefs.min_score, stats.get("scored", 0), stats.get("filtered_out", 0)),
    ]


def render_markdown(profile: Profile, prefs: Preferences, entries: List[Entry], stats: Dict[str, int]) -> str:
    lines = ["# Ofertas para %s — %s" % (profile.name or "vos", datetime.now().strftime("%Y-%m-%d %H:%M")), ""]
    lines += ["- " + l for l in _header_lines(profile, prefs, entries, stats)] + [""]
    if not entries:
        lines.append("_No hay ofertas que superen el score mínimo. Probá bajar `min_score` o ampliar roles/fuentes._")
    for i, e in enumerate(entries, 1):
        j, m = e.job, e.match
        lines.append("## %d. %s — %s%s" % (i, j.title, j.company or "n/a", "  🆕" if e.is_new else ""))
        lines.append("**Score: %d/100** · %s · %s%s" % (
            m.score, ELIGIBLE_LABEL.get(m.eligible, m.eligible), FIT_LABEL.get(m.seniority_fit, ""), ""))
        meta = [x for x in (j.location, j.salary, j.posted_at[:10]) if x]
        if meta:
            lines.append("📍 " + " · ".join(meta))
        lines += ["", m.summary, ""]
        if m.reasons:
            lines += ["**A favor:**"] + ["- " + r for r in m.reasons] + [""]
        if m.gaps:
            lines += ["**A tener en cuenta:**"] + ["- " + g for g in m.gaps] + [""]
        lines.append("[Ver oferta](%s) · Fuente: %s · `ID: %s`" % (j.url, attribution(j.source), j.id))
        lines.append("")
    lines += ["---", FOOTER, "Marcá el estado con `path-finder mark applied|saved|discarded <ID>`."]
    return "\n".join(lines) + "\n"


CSS = """
:root{--bg:#fff;--fg:#1a1a1a;--muted:#666;--card:#f6f7f9;--line:#e1e4e8;--link:#0b5fff;--good:#1a7f37;--mid:#9a6700;--low:#8250df}
@media (prefers-color-scheme:dark){:root{--bg:#14161a;--fg:#e8e8e8;--muted:#9aa0a6;--card:#1d2026;--line:#2d3139;--link:#6ea8ff;--good:#3fb950;--mid:#d29922;--low:#a371f7}}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.5 system-ui,sans-serif}
main{max-width:860px;margin:0 auto;padding:24px 16px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px;margin:16px 0}
h1{font-size:1.5rem}h2{font-size:1.15rem;margin:0 0 4px}
.score{font-weight:700}.s-hi{color:var(--good)}.s-mid{color:var(--mid)}.s-lo{color:var(--low)}
.meta,.src{color:var(--muted);font-size:.9rem}a{color:var(--link)}
.new{font-size:.75rem;border:1px solid var(--link);border-radius:99px;padding:1px 8px;margin-left:6px}
ul{margin:4px 0 8px 20px;padding:0}code{font-size:.85rem}
"""


def render_html(profile: Profile, prefs: Preferences, entries: List[Entry], stats: Dict[str, int]) -> str:
    esc = html.escape
    parts = [
        "<!doctype html><html lang='es'><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width,initial-scale=1'>",
        "<title>Ofertas — path-finder</title><style>%s</style></head><body><main>" % CSS,
        "<h1>Ofertas para %s</h1>" % esc(profile.name or "vos"),
        "<p class='meta'>%s</p>" % "<br>".join(esc(l) for l in _header_lines(profile, prefs, entries, stats)),
    ]
    if not entries:
        parts.append("<p>No hay ofertas que superen el score mínimo.</p>")
    for i, e in enumerate(entries, 1):
        j, m = e.job, e.match
        cls = "s-hi" if m.score >= 80 else "s-mid" if m.score >= 65 else "s-lo"
        meta = " · ".join(esc(x) for x in (j.location, j.salary, j.posted_at[:10]) if x)
        parts.append("<section class='card'>")
        parts.append("<h2>%d. <a href='%s'>%s</a> — %s%s</h2>" % (
            i, esc(j.url, quote=True), esc(j.title), esc(j.company or "n/a"),
            "<span class='new'>nueva</span>" if e.is_new else ""))
        parts.append("<div><span class='score %s'>%d/100</span> · %s · %s%s</div>" % (
            cls, m.score, esc(ELIGIBLE_LABEL.get(m.eligible, m.eligible)), esc(FIT_LABEL.get(m.seniority_fit, "")), ""))
        if meta:
            parts.append("<div class='meta'>%s</div>" % meta)
        parts.append("<p>%s</p>" % esc(m.summary))
        if m.reasons:
            parts.append("<strong>A favor</strong><ul>%s</ul>" % "".join("<li>%s</li>" % esc(r) for r in m.reasons))
        if m.gaps:
            parts.append("<strong>A tener en cuenta</strong><ul>%s</ul>" % "".join("<li>%s</li>" % esc(g) for g in m.gaps))
        parts.append("<div class='src'>Fuente: %s · <code>%s</code></div></section>" % (
            esc(attribution(j.source)), esc(j.id)))
    parts.append("<p class='meta'>%s</p></main></body></html>" % esc(FOOTER))
    return "\n".join(parts)


def write_reports(
    out_dir: Path, profile: Profile, prefs: Preferences, entries: List[Entry], stats: Dict[str, int]
) -> Tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    md_path, html_path = out_dir / ("%s.md" % stamp), out_dir / ("%s.html" % stamp)
    md_path.write_text(render_markdown(profile, prefs, entries, stats), encoding="utf-8")
    html_path.write_text(render_html(profile, prefs, entries, stats), encoding="utf-8")
    return md_path, html_path
