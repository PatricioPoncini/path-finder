"""Interfaz de línea de comandos: init | profile | prefs | search | history | mark | sources (sin IA)."""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from rich.console import Console
from rich.prompt import Prompt
from rich.table import Table

from . import areas as areas_mod
from . import config
from .config import SetupError
from .filters import apply_filters, parse_date
from .prefs import normalize_seniority, preferences_from_profile, review_profile, run_wizard, split_list
from .profile import extract_profile
from .ranking import rank_job, rank_jobs
from .report import build_entries, write_reports
from .roles import LEVEL_INDEX, PRESETS, resolve_roles
from .sources import SOURCES, active_sources, fetch_all
from .store import STATUSES, Store

console = Console()


def resolve_with_flags(text: str):
    """--roles "Sr PM, PO" -> (títulos, niveles explícitos, áreas, ¿algún rol sin nivel?)."""
    tokens = split_list(text)
    titles, levels, found_areas = resolve_roles(tokens)
    return titles, levels, found_areas, any(not resolve_roles([t])[1] for t in tokens)


def _ask(question: str, default: str) -> str:
    return Prompt.ask(question, default=default, show_default=bool(default), console=console)


# --- init -------------------------------------------------------------------------------------
def cmd_init(args: argparse.Namespace) -> int:
    if args.prefs_only:
        profile = config.load_profile()
        base = config.load_prefs() if config.prefs_path().is_file() else preferences_from_profile(profile)
    else:
        cv = args.cv or Prompt.ask("Ruta de tu CV (PDF, .txt o .md)", console=console)
        linkedin = args.linkedin if args.linkedin is not None else (
            "" if args.yes else Prompt.ask("Tu URL de LinkedIn (opcional, solo se guarda en el perfil)",
                                           default="", show_default=False, console=console))
        console.print("Leyendo tu CV…")
        profile = extract_profile(
            Path(cv), linkedin_url=linkedin,
            extra_text_path=Path(args.extra_text) if args.extra_text else None)
        console.print("Esto es lo que detecté (es aproximado, podés corregirlo):")
        _show_profile(profile)
        if not args.yes:
            profile = review_profile(profile, _ask)
        config.save_profile(profile)
        console.print("[green]Perfil guardado[/green] en %s" % config.profile_path())
        base = preferences_from_profile(profile)

    # Flags explícitos pisan los defaults (útil para scripting y para --yes)
    if args.areas:
        known = areas_mod.load_areas()
        base.areas = [a for a in split_list(args.areas.lower()) if a in known] or base.areas
    if args.roles:
        titles, levels, found_areas, unleveled = resolve_with_flags(args.roles)
        base.target_roles = titles or base.target_roles
        if levels:  # "Sr PM" fija el nivel; roles sin nivel (ej. "PO") conservan el de antes
            base.seniority = sorted(set(levels) | (set(base.seniority) if unleveled else set()), key=lambda x: LEVEL_INDEX[x])
        base.areas = base.areas or found_areas
    if args.seniority:
        base.seniority = normalize_seniority(split_list(args.seniority)) or base.seniority
    if args.modes:
        base.work_modes = [m for m in split_list(args.modes.lower()) if m in ("remote", "hybrid", "onsite")] or base.work_modes
    if args.job_languages:
        from .lang import normalize_languages
        base.job_languages = normalize_languages(split_list(args.job_languages)) or base.job_languages
    if args.country:
        from .prefs import default_regions
        base.candidate_country = args.country
        base.eligible_regions = default_regions(args.country)

    prefs = base if args.yes else run_wizard(base, _ask, profile)
    config.save_prefs(prefs)
    console.print("[green]Preferencias guardadas[/green] en %s (podés editarlas a mano)." % config.prefs_path())
    console.print("Siguiente paso: [bold]path-finder search[/bold]  ")
    return 0


def _show_profile(profile) -> None:
    t = Table(show_header=False, box=None)
    for label, value in (
        ("Nombre", profile.name), ("Título", profile.headline),
        ("País", profile.country), ("Experiencia", "%s años (%s)" % (profile.years_experience, profile.seniority_level)),
        ("Áreas", ", ".join(profile.areas) or "(no detectadas: se usa tech)"),
        ("Skills principales", ", ".join(profile.primary_stack)), ("Otras skills", ", ".join(
            s for s in profile.skills if s not in profile.primary_stack)),
        ("Puestos sugeridos", ", ".join(profile.roles_suited)),
    ):
        t.add_row("[bold]%s[/bold]" % label, str(value))
    console.print(t)


def cmd_profile(args: argparse.Namespace) -> int:
    if args.refresh:
        old = config.load_profile() if config.profile_path().is_file() else None
        cv = args.cv or Prompt.ask("Ruta de tu CV", console=console)
        profile = extract_profile(Path(cv), linkedin_url=old.linkedin_url if old else "")
        config.save_profile(profile)
        console.print("[green]Perfil actualizado.[/green]")
    else:
        profile = config.load_profile()
    _show_profile(profile)
    console.print("\nArchivo editable: %s" % config.profile_path())
    return 0


def cmd_prefs(args: argparse.Namespace) -> int:
    if args.edit:
        args.prefs_only, args.cv, args.linkedin, args.extra_text = True, None, None, None
        args.roles = args.seniority = args.modes = args.country = args.job_languages = args.areas = None
        args.yes = False
        return cmd_init(args)
    config.load_prefs()  # valida que exista
    console.print(config.prefs_path().read_text(encoding="utf-8"))
    console.print("Archivo: %s  (editalo a mano o con `path-finder prefs --edit`)" % config.prefs_path())
    return 0


# --- search -----------------------------------------------------------------------------------
def cmd_search(args: argparse.Namespace) -> int:
    profile = config.load_profile()
    prefs = config.load_prefs()
    if args.min_score is not None:
        prefs.min_score = args.min_score
    if args.sources:
        prefs.sources = split_list(args.sources)
    prefs.areas = prefs.areas or profile.areas  # las fuentes eligen categorías según las áreas
    if not (profile.skills or profile.primary_stack):
        console.print("[yellow]Tu perfil no tiene skills: el ranking será pobre. Editá %s o corré `path-finder profile --refresh`.[/yellow]" % config.profile_path())

    with console.status("Buscando ofertas…"):
        jobs, problems = fetch_all(prefs, progress=lambda n, c: console.print("  %-15s %d ofertas" % (n, c)))
    for name, why in problems.items():
        console.print("[yellow]  %s: %s[/yellow]" % (name, why))
    if not jobs:
        console.print("[red]No se obtuvo ninguna oferta de las fuentes.[/red]")
        return 1

    if prefs.job_languages:
        console.print("Idioma de ofertas aceptado: %s" % ", ".join(prefs.job_languages))
    result = apply_filters(jobs, profile, prefs)
    console.print("\n%d ofertas -> %d tras filtros." % (len(jobs), len(result.kept)))
    for reason, count in result.dropped.most_common():
        console.print("  [dim]- %d descartadas: %s[/dim]" % (count, reason))

    store = Store(config.db_path())
    try:
        new_ids = store.upsert_jobs(result.kept)
        statuses = store.statuses(j.id for j in result.kept)
        candidates = [j for j in result.kept if statuses.get(j.id) not in ("applied", "discarded")]
        candidates.sort(key=lambda j: parse_date(j.posted_at) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)

        matches = rank_jobs(candidates, profile, prefs)

        entries = build_entries(candidates, matches, new_ids, prefs.min_score,
                                show_ineligible=args.show_ineligible, only_new=args.only_new)
        stats = {"scored": len(candidates), "filtered_out": sum(result.dropped.values())}
        md_path, html_path = write_reports(config.reports_dir(), profile, prefs, entries, stats)
    finally:
        store.close()

    _print_top(entries)
    console.print("\n[green]Reporte:[/green] %s\n         %s" % (md_path, html_path))
    return 0


def _print_top(entries, n: int = 10) -> None:
    if not entries:
        console.print("\nNo hay ofertas que superen el score mínimo.")
        return
    t = Table(title="Top %d" % min(n, len(entries)))
    for col in ("Score", "Puesto", "Empresa", "Elegible", "ID"):
        t.add_column(col)
    for e in entries[:n]:
        t.add_row(str(e.match.score), e.job.title[:48], e.job.company[:24], e.match.eligible, e.job.id[:40])
    console.print(t)


# --- history / mark / sources -----------------------------------------------------------------
def cmd_history(args: argparse.Namespace) -> int:
    profile, prefs = config.load_profile(), config.load_prefs()
    store = Store(config.db_path())
    try:
        rows = store.list_jobs(args.status, args.limit)
    finally:
        store.close()
    t = Table()
    for col in ("Estado", "Score", "Puesto", "Empresa", "ID"):
        t.add_column(col)
    for job, status in rows:
        t.add_row(status, str(rank_job(job, profile, prefs).score), job.title[:48], job.company[:24], job.id)
    console.print(t)
    return 0


def cmd_mark(args: argparse.Namespace) -> int:
    store = Store(config.db_path())
    try:
        for job_id in args.ids:
            ok = store.set_status(job_id, args.status)
            console.print("%s %s -> %s" % ("[green]ok[/green]" if ok else "[red]no existe[/red]", job_id, args.status))
    finally:
        store.close()
    return 0


def cmd_roles(args: argparse.Namespace) -> int:
    t = Table(title="Roles comunes")
    for col in ("Atajo", "Busca", "Nivel", "Área"):
        t.add_column(col)
    for p in PRESETS:
        t.add_row(p.label, p.title, p.level or "-", p.area)
    console.print(t)
    console.print("Usalos en `path-finder init --roles \"Sr PM, PO\"` o en el asistente. Cualquier otro texto se busca tal cual.")
    return 0


def cmd_areas(args: argparse.Namespace) -> int:
    t = Table(title="Áreas")
    for col in ("Id", "Nombre", "Skills", "Roles"):
        t.add_column(col)
    for a in areas_mod.load_areas().values():
        t.add_row(a.id, a.label, str(len(a.skills)), ", ".join(r.title for r in a.roles)[:70])
    console.print(t)
    console.print("Sumá o pisá áreas con archivos YAML en %s (mismo formato que path_finder/areas/*.yaml)." % (config.home_dir() / "areas"))
    return 0


def cmd_sources(args: argparse.Namespace) -> int:
    enabled = active_sources(config.load_prefs()) if config.prefs_path().is_file() else []
    t = Table()
    for col in ("Fuente", "Activa", "Disponible", "Sitio"):
        t.add_column(col)
    for name, s in SOURCES.items():
        t.add_row(name, "sí" if name in enabled else "no", s.available() or "sí", s.homepage)
    console.print(t)
    console.print("Activá/desactivá fuentes en `sources:` de %s" % config.prefs_path())
    return 0


# --- parser -----------------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="path-finder", description="Buscá ofertas de trabajo y ordenalas según tu CV (reglas locales, sin IA).")
    sub = p.add_subparsers(dest="command", required=True)

    i = sub.add_parser("init", help="Cargar tu CV y tus preferencias (primer paso)")
    i.add_argument("--cv", help="Ruta del CV (PDF, .txt, .md)")
    i.add_argument("--linkedin", help="URL de LinkedIn (solo se guarda en el perfil)")
    i.add_argument("--extra-text", help="Texto extra del perfil (ej. 'Acerca de' de LinkedIn) en .txt/.md")
    i.add_argument("--prefs-only", action="store_true", help="No volver a leer el CV; solo editar preferencias")
    i.add_argument("--roles", help='Puestos separados por coma; acepta atajos: "Sr PM, PO, TL, Sr Software Engineer"')
    i.add_argument("--areas", help="Áreas separadas por coma: tech, product, design, data")
    i.add_argument("--seniority", help="junior, ssr/mid, sr/senior, lead/TL, expert/staff, head (separados por coma)")
    i.add_argument("--modes", help="remote, hybrid, onsite (separados por coma)")
    i.add_argument("--country", help="País donde vivís")
    i.add_argument("--job-languages", help="Idiomas aceptados en las ofertas, ej. es o es,en")
    i.add_argument("--yes", "-y", action="store_true", help="No preguntar: aceptar defaults y flags")
    i.set_defaults(func=cmd_init)

    pr = sub.add_parser("profile", help="Ver o regenerar tu perfil")
    pr.add_argument("--refresh", action="store_true", help="Volver a extraer el perfil del CV")
    pr.add_argument("--cv")
    pr.set_defaults(func=cmd_profile)

    pf = sub.add_parser("prefs", help="Ver o editar tus preferencias")
    pf.add_argument("--edit", action="store_true", help="Volver a correr el asistente de preferencias")
    pf.set_defaults(func=cmd_prefs)

    s = sub.add_parser("search", help="Buscar, ordenar y generar el reporte")
    s.add_argument("--min-score", type=int, help="Score mínimo para aparecer en el reporte")
    s.add_argument("--only-new", action="store_true", help="Reporte solo con ofertas vistas por primera vez")
    s.add_argument("--show-ineligible", action="store_true", help="Incluir ofertas donde no podés aplicar")
    s.add_argument("--sources", help="Fuentes a usar esta vez (separadas por coma)")
    s.set_defaults(func=cmd_search)

    h = sub.add_parser("history", help="Ofertas vistas y su estado")
    h.add_argument("--status", choices=STATUSES)
    h.add_argument("--limit", type=int, default=30)
    h.set_defaults(func=cmd_history)

    m = sub.add_parser("mark", help="Marcar ofertas: applied | saved | discarded | new")
    m.add_argument("status", choices=STATUSES)
    m.add_argument("ids", nargs="+", help="IDs mostrados en el reporte (ej. remotive:123)")
    m.set_defaults(func=cmd_mark)

    ro = sub.add_parser("roles", help="Listar roles comunes (PM, PO, TL, Sr Software Engineer...)")
    ro.set_defaults(func=cmd_roles)

    ar = sub.add_parser("areas", help="Listar áreas profesionales (tech, product, design, data...)")
    ar.set_defaults(func=cmd_areas)

    so = sub.add_parser("sources", help="Listar fuentes de ofertas")
    so.set_defaults(func=cmd_sources)
    return p


def main(argv: Optional[List[str]] = None) -> int:
    config.load_env()
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except SetupError as e:
        console.print("[red]%s[/red]" % e)
        return 2
    except KeyboardInterrupt:
        console.print("\nCancelado.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
