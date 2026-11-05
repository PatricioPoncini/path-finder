"""Interfaz de línea de comandos: init | profile | prefs | search | history | mark | sources."""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from rich.console import Console
from rich.prompt import Prompt
from rich.table import Table

from . import config
from .claude import DEFAULT_MODEL, Claude, ClaudeError
from .config import SetupError
from .filters import apply_filters, parse_date
from .matcher import estimate_tokens, build_system, heuristic_match, score_jobs
from .prefs import normalize_seniority, preferences_from_profile, run_wizard, split_list
from .profile import extract_profile
from .report import build_entries, write_reports
from .sources import SOURCES, fetch_all
from .store import STATUSES, Store

console = Console()


def _ask(question: str, default: str) -> str:
    return Prompt.ask(question, default=default, show_default=bool(default), console=console)


def _score_key(profile, prefs) -> str:
    return "%s:%s" % (profile.fingerprint(), prefs.scoring_fingerprint())


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
        console.print("Analizando tu CV con Claude…")
        profile = extract_profile(
            Claude(args.model or DEFAULT_MODEL), Path(cv), linkedin_url=linkedin,
            extra_text_path=Path(args.extra_text) if args.extra_text else None)
        config.save_profile(profile)
        console.print("[green]Perfil guardado[/green] en %s" % config.profile_path())
        _show_profile(profile)
        base = preferences_from_profile(profile)

    # Flags explícitos pisan los defaults (útil para scripting y para --yes)
    if args.roles:
        base.target_roles = split_list(args.roles)
    if args.seniority:
        base.seniority = normalize_seniority(split_list(args.seniority)) or base.seniority
    if args.modes:
        base.work_modes = [m for m in split_list(args.modes.lower()) if m in ("remote", "hybrid", "onsite")] or base.work_modes
    if args.country:
        from .prefs import default_regions
        base.candidate_country = args.country
        base.eligible_regions = default_regions(args.country)
    if args.model:
        base.model = args.model

    prefs = base if args.yes else run_wizard(base, _ask, profile)
    config.save_prefs(prefs)
    console.print("[green]Preferencias guardadas[/green] en %s (podés editarlas a mano)." % config.prefs_path())
    console.print("Siguiente paso: [bold]jobbot search[/bold]  (probá antes con --dry-run)")
    return 0


def _show_profile(profile) -> None:
    t = Table(show_header=False, box=None)
    for label, value in (
        ("Nombre", profile.name), ("Título", profile.headline),
        ("País", profile.country), ("Experiencia", "%s años (%s)" % (profile.years_experience, profile.seniority_level)),
        ("Stack principal", ", ".join(profile.primary_stack)), ("Puestos sugeridos", ", ".join(profile.roles_suited)),
        ("Idiomas", ", ".join("%s (%s)" % (l.get("language"), l.get("level")) for l in profile.languages)),
    ):
        t.add_row("[bold]%s[/bold]" % label, str(value))
    console.print(t)


def cmd_profile(args: argparse.Namespace) -> int:
    if args.refresh:
        old = config.load_profile() if config.profile_path().is_file() else None
        cv = args.cv or Prompt.ask("Ruta de tu CV", console=console)
        profile = extract_profile(Claude(args.model or DEFAULT_MODEL), Path(cv),
                                  linkedin_url=old.linkedin_url if old else "")
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
        args.roles = args.seniority = args.modes = args.country = None
        args.yes = False
        return cmd_init(args)
    config.load_prefs()  # valida que exista
    console.print(config.prefs_path().read_text(encoding="utf-8"))
    console.print("Archivo: %s  (editalo a mano o con `jobbot prefs --edit`)" % config.prefs_path())
    return 0


# --- search -----------------------------------------------------------------------------------
def cmd_search(args: argparse.Namespace) -> int:
    profile = config.load_profile()
    prefs = config.load_prefs(args.model)
    if args.min_score is not None:
        prefs.min_score = args.min_score
    if args.sources:
        prefs.sources = split_list(args.sources)
    limit = args.limit or prefs.max_jobs_per_run

    with console.status("Buscando ofertas…"):
        jobs, problems = fetch_all(prefs, progress=lambda n, c: console.print("  %-15s %d ofertas" % (n, c)))
    for name, why in problems.items():
        console.print("[yellow]  %s: %s[/yellow]" % (name, why))
    if not jobs:
        console.print("[red]No se obtuvo ninguna oferta de las fuentes.[/red]")
        return 1

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

        key = _score_key(profile, prefs)
        matches = {}
        if args.no_llm:
            matches = {j.id: heuristic_match(j, profile, prefs) for j in candidates}
            todo, failed, claude = [], [], None
        else:
            matches = store.get_scores((j.id for j in candidates), key)
            pending = [j for j in candidates if j.id not in matches]
            todo = pending[:limit]
            console.print("%d ya puntuadas antes (caché), %d por puntuar ahora%s." % (
                len(matches), len(todo),
                " (%d quedan para la próxima corrida; subí --limit)" % (len(pending) - len(todo)) if len(pending) > len(todo) else ""))
            failed, claude = [], None

        if args.dry_run:
            if todo:
                calls, tin, tout = estimate_tokens(build_system(profile, prefs), todo, prefs.batch_size)
                console.print("\n[bold]Dry-run[/bold]: %d llamadas a %s, ~%d tokens de entrada y ~%d de salida. "
                              "Revisá el precio vigente de tu modelo en anthropic.com/pricing." % (calls, prefs.model, tin, tout))
            console.print("No se llamó a Claude ni se generó reporte.")
            return 0

        if todo:
            claude = Claude(prefs.model)
            with console.status("Puntuando con Claude…") as status:
                new_matches, failed = score_jobs(
                    claude, profile, prefs, todo,
                    on_batch=lambda done, total: status.update("Puntuando con Claude… %d/%d" % (done, total)))
            store.save_scores(new_matches, key)
            matches.update({m.job_id: m for m in new_matches})
            if failed:
                console.print("[yellow]%d ofertas no se pudieron puntuar (se reintentan la próxima vez).[/yellow]" % len(failed))

        entries = build_entries(candidates, matches, new_ids, prefs.min_score,
                                show_ineligible=args.show_ineligible, only_new=args.only_new)
        stats = {"scored": len(todo) if not args.no_llm else len(candidates), "filtered_out": sum(result.dropped.values())}
        md_path, html_path = write_reports(config.reports_dir(), profile, prefs, entries, stats)
    finally:
        store.close()

    _print_top(entries)
    console.print("\n[green]Reporte:[/green] %s\n         %s" % (md_path, html_path))
    if claude:
        u = claude.usage
        console.print("[dim]Uso de API: %d llamadas, %d tokens in (+%d de caché), %d out[/dim]" % (
            u.calls, u.input_tokens, u.cache_read_tokens, u.output_tokens))
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
        rows = store.list_jobs(args.status, args.limit, _score_key(profile, prefs))
    finally:
        store.close()
    t = Table()
    for col in ("Estado", "Score", "Puesto", "Empresa", "ID"):
        t.add_column(col)
    for job, status, match in rows:
        t.add_row(status, str(match.score) if match else "-", job.title[:48], job.company[:24], job.id)
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


def cmd_sources(args: argparse.Namespace) -> int:
    enabled = config.load_prefs().sources if config.prefs_path().is_file() else []
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
    p = argparse.ArgumentParser(prog="jobbot", description="Buscá ofertas de trabajo puntuadas contra tu CV con Claude.")
    sub = p.add_subparsers(dest="command", required=True)

    i = sub.add_parser("init", help="Cargar tu CV y tus preferencias (primer paso)")
    i.add_argument("--cv", help="Ruta del CV (PDF, .txt, .md)")
    i.add_argument("--linkedin", help="URL de LinkedIn (solo se guarda en el perfil)")
    i.add_argument("--extra-text", help="Texto extra del perfil (ej. 'Acerca de' de LinkedIn) en .txt/.md")
    i.add_argument("--prefs-only", action="store_true", help="No volver a leer el CV; solo editar preferencias")
    i.add_argument("--roles", help="Puestos separados por coma")
    i.add_argument("--seniority", help="junior, ssr/mid, sr/senior, lead (separados por coma)")
    i.add_argument("--modes", help="remote, hybrid, onsite (separados por coma)")
    i.add_argument("--country", help="País donde vivís")
    i.add_argument("--model", help="Modelo de Claude a usar")
    i.add_argument("--yes", "-y", action="store_true", help="No preguntar: aceptar defaults y flags")
    i.set_defaults(func=cmd_init)

    pr = sub.add_parser("profile", help="Ver o regenerar tu perfil")
    pr.add_argument("--refresh", action="store_true", help="Volver a extraer el perfil del CV")
    pr.add_argument("--cv")
    pr.add_argument("--model")
    pr.set_defaults(func=cmd_profile)

    pf = sub.add_parser("prefs", help="Ver o editar tus preferencias")
    pf.add_argument("--edit", action="store_true", help="Volver a correr el asistente de preferencias")
    pf.add_argument("--model")
    pf.set_defaults(func=cmd_prefs)

    s = sub.add_parser("search", help="Buscar, puntuar y generar el reporte")
    s.add_argument("--limit", type=int, help="Máximo de ofertas nuevas a puntuar con Claude")
    s.add_argument("--min-score", type=int, help="Score mínimo para aparecer en el reporte")
    s.add_argument("--no-llm", action="store_true", help="Sin Claude: score aproximado por coincidencia de skills")
    s.add_argument("--dry-run", action="store_true", help="Mostrar qué se haría y el costo estimado, sin llamar a Claude")
    s.add_argument("--only-new", action="store_true", help="Reporte solo con ofertas vistas por primera vez")
    s.add_argument("--show-ineligible", action="store_true", help="Incluir ofertas donde no podés aplicar")
    s.add_argument("--sources", help="Fuentes a usar esta vez (separadas por coma)")
    s.add_argument("--model", help="Modelo de Claude para esta corrida")
    s.set_defaults(func=cmd_search)

    h = sub.add_parser("history", help="Ofertas vistas y su estado")
    h.add_argument("--status", choices=STATUSES)
    h.add_argument("--limit", type=int, default=30)
    h.set_defaults(func=cmd_history)

    m = sub.add_parser("mark", help="Marcar ofertas: applied | saved | discarded | new")
    m.add_argument("status", choices=STATUSES)
    m.add_argument("ids", nargs="+", help="IDs mostrados en el reporte (ej. remotive:123)")
    m.set_defaults(func=cmd_mark)

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
    except ClaudeError as e:
        console.print("[red]%s[/red]" % e)
        return 1
    except KeyboardInterrupt:
        console.print("\nCancelado.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
