# path-finder

Buscador de empleos que **lee tu CV, trae ofertas de varias fuentes públicas y las ordena según lo que vos buscás**.
Te deja un reporte (Markdown y HTML) con un score de 0 a 100, por qué encaja, qué le falta y, algo clave si vivís fuera
de EE.UU. o Europa, **si realmente podés aplicar desde tu país**.

Funciona **sin IA, sin API keys y sin costo**: todo se calcula con reglas locales. Lo que busca cada persona se guarda
una vez y de ahí salen las búsquedas. Sirve para **developers, producto (PM/PO), diseño y datos**, con roles comunes a un paso
(`Sr PM`, `PO`, `TL`, `Sr Software Engineer`, `Expert`…); ver [Áreas y roles comunes](#áreas-y-roles-comunes).

## Requisitos

- Python 3.9 o superior. Nada más (no hay cuentas ni claves).

## Instalación

```bash
git clone <este-repo> path-finder && cd path-finder
python3 -m venv .venv
.venv/bin/pip install --upgrade pip          # el pip viejo de macOS no instala proyectos con pyproject
.venv/bin/pip install -e .
source .venv/bin/activate                    # para usar `path-finder` directo (si no: .venv/bin/path-finder)
```

## Uso

### 1. Configurar (una sola vez)

```bash
path-finder init
```

Te pide la ruta de tu CV (PDF con texto seleccionable, `.txt` o `.md`) y **detecta áreas, skills, años de experiencia, país y
puestos** con reglas (vocabularios por área, rangos de fechas). Es aproximado: te muestra lo detectado, propone términos
frecuentes de tu CV que no conoce y te deja corregir todo. Después pregunta áreas, puestos (con un menú de roles comunes),
imprescindibles, seniority, modalidad (remoto/híbrido/presencial), país, **idioma de las ofertas**,
tecnologías que preferís o querés evitar y palabras a excluir. Cada pregunta propone un valor: con Enter lo aceptás, con `-` borrás la lista.

Se guarda en `data/profile.json` y `data/preferences.yaml`, ambos editables a mano.

Modo no interactivo: `path-finder init --cv mi_cv.pdf --roles "Sr Software Engineer" --country Argentina --modes remote --job-languages es --yes`

Ejemplos con atajos: `path-finder init --cv cv.pdf --roles "Sr PM, PO" --yes` (producto), `--roles "TL"` (tech lead),
`--roles "UX/UI Designer, Sr Product Designer" --areas design`.

### 2. Buscar

```bash
path-finder search
```

Trae las ofertas, filtra, ordena y deja el reporte en `data/reports/AAAA-MM-DD_HHMMSS.html` (y `.md`) más el top 10 en la
terminal. Las ofertas que aparecen por primera vez se marcan como **nueva**.

| Opción | Qué hace |
|---|---|
| `--min-score N` | Score mínimo para aparecer en el reporte (default 40) |
| `--only-new` | Reporte solo con ofertas vistas por primera vez |
| `--show-ineligible` | Incluye ofertas donde no podrías aplicar por tu ubicación |
| `--sources a,b` | Usar solo esas fuentes esta vez |

### 3. Llevar el seguimiento

```bash
path-finder mark applied himalayas:82565a736b    # applied | saved | discarded | new  (el ID aparece en el reporte)
path-finder history --status applied
```

Las ofertas `applied` y `discarded` no vuelven a aparecer en búsquedas futuras.

### Otros comandos

`path-finder profile` (ver el perfil; `--refresh --cv nuevo.pdf` lo regenera), `path-finder prefs` (ver; `--edit` para rehacer el
asistente), `path-finder sources` (fuentes disponibles), `path-finder roles` (roles comunes y atajos), `path-finder areas` (áreas cargadas).

## Áreas y roles comunes

Cada **área** es un paquete YAML (`path_finder/areas/*.yaml`) con su vocabulario de skills (con alias), catálogo de roles (en
inglés y español), categorías de las fuentes que le corresponden y los pesos del ranking. Vienen cuatro:

| Área | Id | Roles que reconoce (ejemplos) |
|---|---|---|
| Tecnología | `tech` | Software/Backend/Frontend/Full Stack Engineer, Mobile, DevOps, SRE, QA, Tech Lead, Engineering Manager |
| Producto | `product` | Product Manager, Product Owner, Head of Product, Product Operations |
| Diseño | `design` | UX/UI Designer, Product Designer, Visual Designer, UX Researcher, Head of Design |
| Datos | `data` | Data Analyst, Data Scientist, Data Engineer, ML Engineer, Head of Data |

`init` detecta tu(s) área(s) por el CV y activa solo las fuentes y categorías que corresponden (por ejemplo, el feed de producto de
We Work Remotely o la categoría de diseño de Get on Board). En producto y diseño el título pesa más en el score, porque sus
avisos mencionan menos herramientas que los de tecnología.

**Roles comunes**: se pueden escribir como atajo y traen su nivel. `Sr PM` = Product Manager + senior; `PO` = Product Owner;
`TL` = Tech Lead (nivel lead); `Expert` = Software Engineer nivel expert (staff/principal); `Sr Software Engineer` = Software
Engineer senior. Cualquier otro texto se busca tal cual. Los niveles son `junior < mid < senior < lead < expert < head`;
"Product Manager" es un rol, no un nivel: el nivel sale de palabras como *Senior*, *Staff*, *Group*, *Director*.

**Agregar un área propia** (por ejemplo, legal o marketing): creá `data/areas/<id>.yaml` con las claves de
`path_finder/areas/product.yaml` (`id`, `label`, `skills`, `roles` son obligatorias; el resto es opcional). Se suma a las incluidas,
o pisa una con el mismo `id`. Verificalo con `path-finder areas`.

## Cómo se calcula el score

Cada oferta parte de 20 puntos y suma o resta:

| Regla | Puntos |
|---|---|
| Cada tecnología de tu **stack principal** presente (máx. 5) | +9 |
| Cada otra skill del perfil presente (máx. 5) | +3 |
| Cada tecnología de `preferred_stack` que no está en el perfil (máx. 3) | +4 |
| El título coincide con tus `target_roles` | +10 |
| El seniority del título está entre los que buscás | +8 |
| Título más junior de lo que buscás | −20 |
| Título de más nivel (lead/staff/principal/manager) | −10 |
| Pide más años de experiencia que los tuyos (+2 o más / +5 o más) | −10 / −20 |
| Menciona una tecnología de `avoid_stack` | −15 c/u |
| Salario declarado por debajo de `min_salary_usd` | −10 |
| Elegibilidad `yes` | +5 |
| Elegibilidad `no` | el score se limita a 25 |

Las tecnologías se buscan con alias (`Golang` = Go, `k8s` = Kubernetes, `Postgres` = PostgreSQL). Las de hasta 3 letras
(`Go`, `AWS`) respetan mayúsculas para no confundirlas con palabras comunes.

**Elegibilidad** (`yes` / `no` / `unclear`): primero las restricciones geográficas estructuradas que dan algunas fuentes
(Remotive, Himalayas, We Work Remotely) contra `eligible_regions`; si no hay, patrones del texto como "US only", "must be
located in…", "authorized to work in the US", y menciones de tu región o de "worldwide".

## Idioma de las ofertas

`job_languages: [es]` hace que path-finder descarte las ofertas cuya descripción no esté en español. El idioma se detecta del texto
con un conteo de palabras frecuentes (es, en, pt, it, de, fr), sin dependencias. Si el texto es muy corto o ambiguo, la oferta
**se conserva** (no se descarta por duda). Las ofertas bilingües se clasifican por el idioma dominante del texto.

Con `es`, además de filtrar: se activa Get on Board, se buscan también títulos en español y el filtro de títulos acepta
"desarrollador/ingeniero backend". Hoy es la única fuente en español con API pública que pude verificar; los portales grandes
(Computrabajo, Bumeran, ZonaJobs, LinkedIn, Indeed) no tienen API pública y scrapear su HTML va contra sus términos, así que
no están incluidos. Ojo: Get on Board deja publicados los avisos por mucho tiempo, y `max_age_days` (30 por defecto) descarta
los viejos; subilo si ves pocos resultados.

## Preferencias (`data/preferences.yaml`)

| Campo | Para qué sirve |
|---|---|
| `target_roles` | Puestos que buscás. Se usan para buscar y para filtrar por título |
| `areas` | `tech`, `product`, `design`, `data` (o las tuyas). Vacío = las de tu perfil |
| `seniority` | `junior`, `mid` (ssr), `senior` (sr), `lead` (TL), `expert` (staff/principal), `head` (director) |
| `must_have` | Imprescindibles: términos que la oferta debería mencionar (suman mucho si están y restan si faltan) |
| `work_modes` | `remote`, `hybrid`, `onsite` |
| `candidate_country` | Tu país; se usa en la elegibilidad |
| `job_languages` | Idiomas aceptados en la descripción de la oferta: `es`, `en`, `pt`, `it`, `de`, `fr`. Descarta las ofertas escritas en otro idioma (ej. con `[es]` no ves avisos en inglés ni italiano). Vacío = cualquiera. Con `es` se activa solo Get on Board y se buscan títulos en español ("desarrollador backend") |
| `eligible_regions` | Palabras que, si aparecen en la restricción geográfica de una oferta, te habilitan (ej. `worldwide`, `latam`, tu país). Ofertas "US only" y similares se descartan |
| `strict_region_filter` | `false` para no descartar por región y dejar solo la marca de elegibilidad |
| `preferred_stack` / `avoid_stack` | Skills o términos que suman o restan (no solo tecnologías) |
| `exclude_keywords` | Palabras que descartan una oferta si están en el título o las etiquetas |
| `title_keywords` / `search_queries` | Frases extra aceptadas en el título / consultas de búsqueda propias |
| `min_salary_usd` | Salario mínimo anual en USD (0 = ignorar) |
| `max_age_days`, `min_score` | Antigüedad máxima y score mínimo del reporte |
| `sources` | Fuentes activas |

## Fuentes de ofertas

| Fuente | Clave | Notas |
|---|---|---|
| Remotive | no | Solo remoto; exige atribución |
| Remote OK | no | Últimas ~100 ofertas + las de los tags del área; exige atribución |
| Himalayas | no | Buen dato de restricciones por país |
| We Work Remotely | no | Feeds RSS: general + categorías de tus áreas (programación, producto, diseño) |
| Arbeitnow | no | Foco Alemania/Europa; muchas no son remotas |
| Get on Board | no | Foco LATAM, muchas ofertas en español; se activa solo si `job_languages` incluye `es`; recorre las categorías de tus áreas |
| Adzuna | sí (gratis) | Requiere `ADZUNA_APP_ID`/`ADZUNA_APP_KEY` en `.env`. **Sin verificar con credenciales reales** |

El reporte incluye siempre el link a la oferta original y la fuente, como piden los términos de Remotive y Remote OK.
No republiques sus ofertas en otros sitios.

## LinkedIn

path-finder **no** consulta LinkedIn. Automatizar tu sesión viola sus términos de uso y puede restringir o bloquear tu cuenta.
Podés guardar tu URL (`--linkedin`) y pasar con `--extra-text` un archivo con el texto de tu perfil para sumar skills a la
detección. Si querés cubrir LinkedIn, las formas seguras son sus alertas de empleo por email o copiar a mano las ofertas.

## Privacidad

Todo (CV, perfil, historial, reportes, `.env`) queda en tu máquina; `data/` y `.env` están en `.gitignore`. Lo único que sale
de tu equipo son las consultas HTTP a las fuentes públicas de ofertas; tu CV no se envía a ningún lado.

## Limitaciones

- El perfil sale de vocabularios por área (tecnología, producto, diseño, datos). Para otra profesión, creá un área propia
  en `data/areas/` o cargá tus skills a mano en `path-finder init` / `data/profile.json`.
- Producto y diseño: sus avisos son más genéricos, así que el score discrimina menos que en tecnología. Usá `must_have`
  (industria, tipo de producto) para afinarlo.
- El score son reglas, no comprensión del texto: sirve para priorizar, no para decidir por vos. Una oferta puede mencionar
  tu stack como "nice to have" o pedir cosas que el ranking no ve.
- La elegibilidad se deduce con patrones y puede fallar: verificala antes de postular.
- El detector de idioma es aproximado y los boards remotos en español tienen pocas ofertas: con `job_languages: [es]` esperá
  una lista corta. Podés sumar `en` para ampliar.
- Las fuentes son boards remotos; no cubren todo el mercado local ni ofertas presenciales.

## Desarrollo

```bash
pip install -e ".[dev]" && python -m pytest -q
```

Arquitectura, convenciones y cómo agregar una fuente: ver [`CLAUDE.md`](CLAUDE.md).
