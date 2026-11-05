# CLAUDE.md — jobbot

Bot de búsqueda de empleo: trae ofertas de fuentes públicas, las filtra sin LLM y las puntúa contra el CV del usuario
con la API de Claude. **Es genérico**: nada de la persona que lo creó está hardcodeado; todo sale de
`data/profile.json` (extraído del CV) y `data/preferences.yaml` (lo que busca). Documentación para humanos: `README.md`.

## Comandos

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"   # requiere pip >= 21.3 (actualizar pip del venv)
.venv/bin/python -m pytest -q          # tests (Claude y red simulados, no gastan nada)
.venv/bin/jobbot init                  # CV -> perfil + preferencias   (necesita ANTHROPIC_API_KEY)
.venv/bin/jobbot search --dry-run      # fuentes reales + filtros + costo estimado, sin llamar a Claude
.venv/bin/jobbot search --no-llm       # reporte con score heurístico, sin API key
.venv/bin/jobbot search                # flujo completo
```

Para probar sin tocar `data/`: `JOBBOT_HOME=/ruta/temporal jobbot ...`.

## Pipeline y módulos (`jobbot/`)

`sources/*` → `filters.py` → `store.py` (caché) → `matcher.py` (Claude) → `report.py`; `cli.py` orquesta.

| Módulo | Responsabilidad |
|---|---|
| `models.py` | `Job`, `Match`, `Profile`, `Preferences` (dataclasses), `html_to_text`, `stable_hash`. `Preferences.scoring_fingerprint()` define qué campos invalidan la caché de scores |
| `config.py` | Rutas (`JOBBOT_HOME` o `./data`), `.env`, carga/guardado de perfil y preferencias; `SetupError` = error para mostrar al usuario tal cual |
| `claude.py` | Único punto de contacto con el SDK. `tool_call()` fuerza salida estructurada vía tool use, cachea el bloque `system`, cuenta uso |
| `profile.py` | CV (PDF con `pypdf`; si el texto es < 200 chars se manda el PDF como documento a Claude) → `Profile` |
| `prefs.py` | Defaults derivados del perfil, wizard, `default_regions(country)` |
| `sources/` | Una clase `Source` por fuente; registro en `sources/__init__.py`. `fetch_all` aísla fallas por fuente |
| `filters.py` | Pre-filtro sin LLM: remoto, antigüedad, título vs roles, junior, keywords excluidas, restricción geográfica, duplicados |
| `matcher.py` | Scoring por lotes (`batch_size`), prompt de sistema con perfil+prefs, `heuristic_match` para `--no-llm` |
| `store.py` | SQLite `data/jobs.db`: ofertas, estado (new/saved/applied/discarded) y scores cacheados por `(job_id, cache_key)` |
| `report.py` | Markdown + HTML (escapado) en `data/reports/` |

## Convenciones y decisiones que no son obvias

- **Python 3.9 compatible** (es el del sistema en macOS): `from __future__ import annotations` en todos los módulos, sin
  `match`, sin `X | Y` fuera de anotaciones, `typing.List/Dict/Optional` en dataclasses.
- **IDs**: `"<fuente>:<id>"`. Si la fuente solo tiene URL, usar `stable_hash(url)[:10]` (los IDs los tipea el usuario en `jobbot mark`).
- **Caché de scores**: clave = `profile.fingerprint() : prefs.scoring_fingerprint()`. Si agregás un campo de preferencias que
  cambia cómo se evalúa, sumalo a `scoring_fingerprint()`; si no afecta el scoring (ej. `min_score`), NO lo sumes.
- **Elegibilidad regional** (clave para quien vive fuera de EE.UU./UE): dos capas. (1) `filters.region_ok` descarta con
  `location_restrictions` estructuradas (Remotive, Himalayas, WWR) que no matcheen `eligible_regions`; (2) Claude juzga
  `eligible: yes/no/unclear` leyendo la descripción, y si es `no` el score se limita a 25 en `matcher._clean`.
  Las fuentes que solo dan `location` informal (Remote OK, Arbeitnow) NO llenan `location_restrictions` a propósito.
- **Costo**: el filtro corre antes de Claude; los scores se cachean; `max_jobs_per_run` topea cada corrida; `--dry-run` estima tokens.
  Modelo por defecto `claude-haiku-5-5` (en `preferences.yaml: model`, env `JOBBOT_MODEL` o `--model`). Extensión pendiente:
  dos etapas (Haiku filtra, Sonnet re-evalúa el top).
- **Respuestas de Claude**: siempre por tool use (`MATCH_TOOL`, `PROFILE_TOOL`), nunca parseando texto libre. Si falta una oferta
  en la respuesta se reintenta el lote una vez; las que sigan faltando quedan sin puntuar y se reintentan en la próxima corrida.
- **Fuentes y términos de uso**: Remotive y Remote OK exigen atribución y link a la oferta original (el reporte ya lo hace);
  no republicar sus ofertas en sitios de terceros. Respetar rate limits (Arbeitnow pide no abusar).
- **LinkedIn NO está integrado, a propósito**: scrapear con sesión logueada viola sus términos y arriesga la cuenta. La URL de
  LinkedIn solo se guarda en `profile.json`. Si se agrega algo, las opciones seguras son alertas por email (IMAP) o pegar la
  oferta a mano; no automatizar el navegador del usuario.
- **Privacidad**: CV, perfil, historial y reportes viven en `data/` (gitignored) y `.env` también. Solo el contenido del CV y las
  ofertas se envían a la API de Anthropic. Nunca commitear `data/` ni `.env`.
- **Idioma**: CLI y docs en español; los resúmenes del reporte salen en `preferences.output_language`.

## Cómo agregar una fuente

1. `jobbot/sources/<nombre>.py`: clase que hereda de `Source`, con `name`, `label`, `homepage` y `fetch(prefs, client) -> List[Job]`
   (parseo en un `@staticmethod _parse(item)` para testearlo). Poblar `location_restrictions` solo si la fuente lo da estructurado.
2. Registrarla en `SOURCES` (`sources/__init__.py`) y, si corresponde, en el default de `Preferences.sources`.
3. Test del parseo con un item de ejemplo en `tests/test_sources_and_prefs.py`. Verificar primero el esquema real con `curl`.

## Estado

- Verificado contra las APIs reales: Remotive, Remote OK, Himalayas, We Work Remotely, Arbeitnow (esquemas al 2026-11-04).
- `adzuna` está implementada pero **no se verificó con credenciales reales**.
- El wrapper de Claude está testeado contra un transporte HTTP simulado (forma del request y parseo); la primera corrida real
  con API key (`jobbot init`, `jobbot search`) todavía no se hizo en este repo.
