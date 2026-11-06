# CLAUDE.md — jobbot

Bot de búsqueda de empleo **sin IA**: trae ofertas de fuentes públicas, las filtra y las ordena contra el CV del usuario con
reglas locales. **Es genérico**: nada de la persona que lo creó está hardcodeado; todo sale de `data/profile.json` (extraído
del CV) y `data/preferences.yaml` (lo que busca). Documentación para humanos: `README.md`.

## Comandos

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"   # requiere pip >= 21.3 (actualizar pip del venv)
.venv/bin/python -m pytest -q          # tests (la red está simulada)
.venv/bin/jobbot init                  # CV -> perfil + preferencias
.venv/bin/jobbot search                # fuentes reales -> filtros -> ranking -> reporte
```

Para probar sin tocar `data/`: `JOBBOT_HOME=/ruta/temporal jobbot ...`.

## Pipeline y módulos (`jobbot/`)

`sources/*` → `filters.py` → `store.py` (historial) → `ranking.py` → `report.py`; `cli.py` orquesta.

| Módulo | Responsabilidad |
|---|---|
| `models.py` | `Job`, `Match`, `Profile`, `Preferences` (dataclasses), `html_to_text`, `stable_hash` |
| `config.py` | Rutas (`JOBBOT_HOME` o `./data`), `.env`, carga/guardado de perfil y preferencias; `SetupError` = error para mostrar al usuario tal cual |
| `areas/` | Paquetes de área (`tech`, `product`, `design`, `data` en YAML) + `load_areas()`/`resolve()`/`vocabulary()`. Cada YAML: `skills` (con alias), `concepts`, `ambiguous`, `roles`, `title_nouns`, `feeds`, `weights`. El usuario suma/pisa áreas con `data/areas/*.yaml` |
| `roles.py` | Niveles (`junior<mid<senior<lead<expert<head`), `title_level`, `level_fit`, presets de roles comunes (`PRESETS`), `resolve_role("Sr PM")` |
| `countries.py` | Países que se detectan en el encabezado de un CV |
| `profile.py` | CV (PDF con `pypdf`, txt, md) → `Profile` con reglas: skills (vocabulario de todas las áreas), `detect_areas`, años por rangos de fechas (ignora educación), puestos, nombre, país, `suggest_terms` (propone, no agrega) |
| `prefs.py` | Defaults derivados del perfil, wizard de preferencias, `review_profile` (corregir lo detectado), `default_regions(country)` |
| `sources/` | Una clase `Source` por fuente; registro en `sources/__init__.py`. `fetch_all` aísla fallas por fuente |
| `lang.py` | Detección de idioma sin dependencias (palabras funcionales por idioma); `normalize_languages` acepta "español", "es", etc. |
| `filters.py` | Pre-filtro: remoto, antigüedad, título vs roles (normaliza back-end/backend; variantes en español si `es`), junior, keywords excluidas, restricción geográfica, idioma de la oferta, duplicados |
| `ranking.py` | `rank_job`: score 0-100 por reglas + `eligibility()` por regex; reasons/gaps salen de plantillas |
| `store.py` | SQLite `data/jobs.db`: ofertas vistas y su estado (new/saved/applied/discarded) |
| `report.py` | Markdown + HTML (escapado) en `data/reports/` |

## Convenciones y decisiones que no son obvias

- **Sin IA, a propósito**: la API de Anthropic se paga aparte de la suscripción y el usuario no quiere depender de ella. No agregar
  llamadas a LLM ni dependencias de red más allá de las fuentes. Si algún día se quiere un scorer con IA, hacerlo como módulo
  opcional enchufable, no mezclado en `ranking.py`.
- **Python 3.9 compatible** (es el del sistema en macOS): `from __future__ import annotations` en todos los módulos, sin
  `match`, sin `X | Y` fuera de anotaciones, `typing.List/Dict/Optional` en dataclasses.
- **IDs**: `"<fuente>:<id>"`. Si la fuente solo tiene URL, usar `stable_hash(url)[:10]` (los IDs los tipea el usuario en `jobbot mark`).
- **Pesos del ranking**: constantes al inicio de `ranking.py` (tabla en el README). Si las cambiás, actualizá la tabla y los tests.
  El score no se persiste: se recalcula en cada corrida y en `history`.
- **Idioma de la oferta** (`Preferences.job_languages`): `filters.job_language` detecta del texto (y usa `Job.language` de la fuente
  solo si el texto no alcanza). Ante duda NO se descarta. `Source.auto_languages` activa fuentes solas (`sources.active_sources`):
  hoy `getonbrd` con `es`. No hay más fuentes en español porque las demás (Computrabajo, Bumeran, ZonaJobs, LinkedIn, Indeed) no
  tienen API pública y scrapearlas va contra sus términos; Torre.ai no respondió a su endpoint no documentado.
- **Todo lo específico de una profesión vive en `areas/*.yaml`**, no en código. No agregues listas de tecnologías, roles o categorías de
  fuentes a módulos Python; sumalos al YAML del área. `tests/test_areas_roles.py` valida los paquetes (claves, regex, alias que apuntan
  a dos skills distintas, `concepts` ⊆ `skills`): si agregás un área o skill, ese test te avisa de conflictos.
- **"manager" no es un nivel**: "Product Manager" es un rol. `roles.title_level` solo cuenta *engineering/people/design/data manager* como `lead`.
  Los nombres de rol que parecen niveles ("Tech Lead", "Head of Product") se buscan enteros (`sources.base.search_queries`, `filters._role_forms`).
- **Alias cortos de rol** (PM, PO, TL, SRE ≤ 3 letras en mayúsculas) se comparan con mayúsculas exactas y límites de palabra (`filters.role_in_title`):
  si no, "pm" matchearía dentro de "development".
- **Rescate por título**: `title_nouns` del área + un término conocido en el título. Mantenelo estricto en producto (sin "manager" a secas) para no traer
  "Sales Manager".
- **Fuentes por área**: las fuentes leen `prefs.areas` (el CLI lo completa con `profile.areas`) y usan `area.feeds`: WWR (`weworkremotely`),
  Get on Board (`getonbrd`, categorías; mezcla modalidades, así que `_parse` marca `remote` False/None según `remote_modality`), Remote OK (`remoteok_tags`).
- **Skills cortas** (≤ 3 letras, o en `ambiguous` del área) se buscan respetando mayúsculas (`Go`, `AWS`, `Gin`) para evitar falsos positivos.
- **Elegibilidad regional** (clave para quien vive fuera de EE.UU./UE): dos capas. (1) `filters.region_ok` descarta con
  `location_restrictions` estructuradas (Remotive, Himalayas, WWR) que no matcheen `eligible_regions`; (2) `ranking.eligibility`
  usa esas restricciones y patrones del texto; si es `no`, el score se limita a 25. Las fuentes que solo dan `location` informal
  (Remote OK, Arbeitnow) NO llenan `location_restrictions` a propósito.
- **Fuentes y términos de uso**: Remotive y Remote OK exigen atribución y link a la oferta original (el reporte ya lo hace);
  no republicar sus ofertas en sitios de terceros. Respetar rate limits (Arbeitnow pide no abusar).
- **LinkedIn NO está integrado, a propósito**: scrapear con sesión logueada viola sus términos y arriesga la cuenta. La URL de
  LinkedIn solo se guarda en `profile.json`. Si se agrega algo, las opciones seguras son alertas por email (IMAP) o pegar la
  oferta a mano; no automatizar el navegador del usuario.
- **Privacidad**: CV, perfil, historial y reportes viven en `data/` (gitignored) y `.env` también. El CV no sale de la máquina.
  Nunca commitear `data/` ni `.env`.
- **Idioma**: CLI, reportes y docs en español.
- **Compatibilidad**: `Preferences.from_dict` ignora campos desconocidos, así que un `preferences.yaml` de la versión con Claude
  (`model`, `notes`, etc.) sigue cargando.

## Cómo agregar una fuente

1. `jobbot/sources/<nombre>.py`: clase que hereda de `Source`, con `name`, `label`, `homepage` y `fetch(prefs, client) -> List[Job]`
   (parseo en un `@staticmethod _parse(item)` para testearlo). Poblar `location_restrictions` solo si la fuente lo da estructurado.
2. Registrarla en `SOURCES` (`sources/__init__.py`) y, si corresponde, en el default de `Preferences.sources`.
3. Test del parseo con un item de ejemplo en `tests/test_sources_and_prefs.py`. Verificar primero el esquema real con `curl`.

## Estado

- Verificado contra las APIs reales: Remotive, Remote OK, Himalayas, We Work Remotely, Arbeitnow (esquemas al 2026-11-04).
- `getonbrd` verificada contra su API real el 2026-11-05 (`/api/v0/search/jobs?remote=true`). Adzuna: la ruta `/ar/` no se pudo confirmar sin credenciales.
- `adzuna` está implementada pero **no se verificó con credenciales reales**.
- Verificado con búsquedas reales (2026-11-05): CV de developer (el de Patricio), y CV de ejemplo de PM, diseño y datos (`tests/fixtures/cv_*.txt`),
  con resultados del área correcta en el top. WWR no tiene categoría de datos; Remote OK solo filtra bien por algunos tags (`product-manager`, `designer`,
  `data-science`): el filtro local de título limpia el resto. Remotive: no se usa `category=` (devolvió lo mismo para todo).
- `jobbot init` y `jobbot search` corridos de punta a punta con un CV real (PDF): detecta nombre, país, ~4 años y el stack.
  Ranking calibrado a ojo con una corrida real (min_score por defecto 40); los pesos se pueden ajustar con más uso.
