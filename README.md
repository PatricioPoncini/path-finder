# jobbot

Buscador de empleos que **lee tu CV, trae ofertas de varias fuentes públicas y las puntúa con Claude** según lo que vos
buscás. Te deja un reporte ordenado (Markdown y HTML) con un score de 0 a 100, por qué encaja, qué le falta y, algo clave
si vivís fuera de EE.UU. o Europa, **si realmente podés aplicar desde tu país**.

Funciona para cualquier persona y cualquier profesión: lo que busca cada uno se guarda una vez y de ahí salen las búsquedas.

## Requisitos

- Python 3.9 o superior
- Una API key de Anthropic ([console.anthropic.com](https://console.anthropic.com/) → API Keys). La API se paga por uso;
  una corrida típica de ~40 ofertas con Haiku cuesta centavos (corré `--dry-run` para ver una estimación de tokens).
  Sin key podés usar `--no-llm` (score aproximado, menos preciso).

## Instalación

```bash
git clone <este-repo> jobbot && cd jobbot
python3 -m venv .venv
.venv/bin/pip install --upgrade pip          # el pip viejo de macOS no instala proyectos con pyproject
.venv/bin/pip install -e .
cp .env.example .env                         # y pegá tu ANTHROPIC_API_KEY adentro
source .venv/bin/activate                    # para usar `jobbot` directo (si no: .venv/bin/jobbot)
```

## Uso

### 1. Configurar (una sola vez)

```bash
jobbot init
```

Te pide la ruta de tu CV (PDF, `.txt` o `.md`), lo analiza con Claude, te muestra el perfil que extrajo y después te hace
unas preguntas: puestos, seniority, modalidad (remoto/híbrido/presencial), país donde vivís, tecnologías que preferís o
querés evitar, palabras a excluir y notas libres para Claude (ej. "prefiero startups", "nada de criptomonedas").
Cada pregunta propone un valor por defecto: con Enter lo aceptás, con `-` borrás la lista.

Se guarda en `data/profile.json` y `data/preferences.yaml`. Ambos son archivos de texto que podés editar a mano.

Modo no interactivo: `jobbot init --cv mi_cv.pdf --roles "Backend Engineer" --seniority "ssr,sr" --country Argentina --modes remote --yes`

### 2. Buscar

```bash
jobbot search --dry-run     # qué haría y cuánto costaría, sin llamar a Claude
jobbot search               # búsqueda completa
```

Al terminar muestra el top 10 y deja el reporte en `data/reports/AAAA-MM-DD_HHMMSS.html` (y `.md`). Las ofertas que ya
puntuó antes no se vuelven a pagar (caché); las que aparecen por primera vez se marcan como **nueva**.

| Opción | Qué hace |
|---|---|
| `--limit N` | Máximo de ofertas nuevas a puntuar en esta corrida (default `max_jobs_per_run`) |
| `--min-score N` | Score mínimo para aparecer en el reporte |
| `--only-new` | Reporte solo con ofertas vistas por primera vez |
| `--show-ineligible` | Incluye ofertas donde Claude detectó que no podés aplicar |
| `--sources a,b` | Usar solo esas fuentes esta vez |
| `--model ID` | Otro modelo de Claude para esta corrida |
| `--no-llm` | Sin API key: score aproximado por coincidencia de skills |

### 3. Llevar el seguimiento

```bash
jobbot mark applied himalayas:82565a736b    # applied | saved | discarded | new  (el ID aparece en el reporte)
jobbot history --status applied
```

Las ofertas `applied` y `discarded` no vuelven a aparecer en búsquedas futuras.

### Otros comandos

`jobbot profile` (ver el perfil; `--refresh --cv nuevo.pdf` lo regenera), `jobbot prefs` (ver; `--edit` para rehacer el
asistente), `jobbot sources` (fuentes disponibles).

## Preferencias (`data/preferences.yaml`)

| Campo | Para qué sirve |
|---|---|
| `target_roles` | Puestos que buscás. Se usan para buscar y para filtrar por título |
| `seniority` | `junior`, `mid` (ssr), `senior` (sr), `lead` |
| `work_modes` | `remote`, `hybrid`, `onsite` |
| `candidate_country` | Tu país; Claude lo usa para juzgar si podés aplicar |
| `eligible_regions` | Palabras que, si aparecen en la restricción geográfica de una oferta, te habilitan (ej. `worldwide`, `latam`, tu país). Ofertas "US only" y similares se descartan antes de gastar tokens |
| `strict_region_filter` | `false` para no descartar por región y que decida solo Claude |
| `preferred_stack` / `avoid_stack` | Tecnologías que suman o restan |
| `exclude_keywords` | Palabras que descartan una oferta si están en el título o las etiquetas |
| `title_keywords` / `search_queries` | Frases extra aceptadas en el título / consultas de búsqueda propias |
| `notes` | Texto libre que se le pasa a Claude |
| `output_language` | Idioma de los resúmenes del reporte |
| `max_age_days`, `min_score`, `max_jobs_per_run`, `batch_size` | Antigüedad máxima, score mínimo, tope de ofertas por corrida y ofertas por llamada |
| `model` | Modelo de Claude (default `claude-haiku-5-5`). Un modelo más grande evalúa mejor los casos ambiguos y cuesta más |
| `sources` | Fuentes activas |

Cambiar `target_roles`, `seniority`, `work_modes`, país, stack, `notes` o `output_language` invalida los scores guardados
(se vuelven a puntuar); el resto no.

## Fuentes de ofertas

| Fuente | Clave | Notas |
|---|---|---|
| Remotive | no | Solo remoto; exige atribución |
| Remote OK | no | Últimas ~100 ofertas; exige atribución |
| Himalayas | no | Buen dato de restricciones por país |
| We Work Remotely | no | Feeds RSS |
| Arbeitnow | no | Foco Alemania/Europa; muchas no son remotas |
| Adzuna | sí (gratis) | Requiere `ADZUNA_APP_ID`/`ADZUNA_APP_KEY`. **Sin verificar con credenciales reales** |

El reporte incluye siempre el link a la oferta original y la fuente, como piden los términos de Remotive y Remote OK.
No republiques sus ofertas en otros sitios.

## LinkedIn

jobbot **no** consulta LinkedIn. Automatizar tu sesión viola sus términos de uso y puede restringir o bloquear tu cuenta.
Podés guardar tu URL de LinkedIn en el perfil (`--linkedin`) y pasar con `--extra-text` un archivo con el texto de tu
perfil ("Acerca de", experiencia) para enriquecer la extracción. Si querés cubrir LinkedIn, las formas seguras son sus alertas
de empleo por email o copiar a mano las ofertas que te interesen.

## Privacidad

Todo (CV, perfil, historial, reportes, `.env`) queda en tu máquina; `data/` y `.env` están en `.gitignore`. A Anthropic solo se
envía el contenido de tu CV y de las ofertas que se puntúan.

## Limitaciones

- Los scores son una opinión de un modelo sobre el texto de la oferta: sirven para priorizar, no para decidir por vos.
- Las fuentes son boards remotos; no cubren todo el mercado local ni ofertas presenciales.
- La elegibilidad regional se deduce del texto de la oferta y puede fallar: verificala antes de postular.

## Desarrollo

```bash
pip install -e ".[dev]" && python -m pytest -q
```

Arquitectura, convenciones y cómo agregar una fuente: ver [`CLAUDE.md`](CLAUDE.md).
