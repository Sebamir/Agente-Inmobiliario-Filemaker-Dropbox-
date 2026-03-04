# Agente de Búsqueda Inmobiliaria

Sistema multiusuario para búsqueda de inmuebles que integra **FileMaker** (fuente de datos) con **Dropbox** (almacenamiento de imágenes), expuesto mediante una API REST (FastAPI) y una interfaz web (Streamlit) con soporte de búsqueda por lenguaje natural vía GPT-4o-mini.

---

## Índice

1. [Arquitectura](#arquitectura)
2. [Stack tecnológico](#stack-tecnológico)
3. [Estructura del proyecto](#estructura-del-proyecto)
4. [Flujo de datos](#flujo-de-datos)
5. [Instalación y configuración](#instalación-y-configuración)
6. [Levantar el sistema](#levantar-el-sistema)
7. [Uso de la API](#uso-de-la-api)
8. [Seguridad](#seguridad)
9. [Decisiones de diseño](#decisiones-de-diseño)
10. [Pendientes](#pendientes)

---

## Arquitectura

```
┌──────────────────────────────────────────────────────────────┐
│                       Docker Network                          │
│                                                              │
│  ┌──────────────┐   POST /api/v1/agent/search               │
│  │  Streamlit   │ ───────────────────────────►              │
│  │  :8501       │              ┌──────────────────────────┐  │
│  │  text_area   │              │   FastAPI (uvicorn) :8000 │  │
│  │  + botón     │              └────────────┬─────────────┘  │
│  └──────────────┘                           │                 │
│                                ┌────────────▼─────────────┐  │
│                                │      Orquestador          │  │
│                                │  natural_language_search()│  │
│                                └──────┬──────────┬─────────┘  │
│                                       │          │             │
└───────────────────────────────────────┼──────────┼────────────┘
                                        │          │
              ┌─────────────────────────▼──┐  ┌───▼──────────────────┐
              │   FileMaker Data API        │  │   Dropbox API v2      │
              │   (solo lectura)            │  │   - imagen más nueva  │
              └─────────────────────────────┘  │   - link a carpeta    │
                        ▲                      └───────────────────────┘
              ┌─────────┴──────────┐
              │  OpenAI GPT-4o-mini │
              │  (extrae filtros FM)│
              └────────────────────┘
```

---

## Stack tecnológico

| Capa              | Tecnología                | Versión      |
|-------------------|---------------------------|--------------|
| API Backend       | FastAPI + Uvicorn         | 0.111 / 0.29 |
| FileMaker         | python-fmrest             | 1.7.0        |
| Dropbox           | dropbox SDK               | 12.0.2       |
| Agente NL         | OpenAI GPT-4o-mini        | openai 1.35  |
| Interfaz          | Streamlit                 | 1.35.0       |
| Configuración     | pydantic-settings         | 2.3.0        |
| Reintentos        | tenacity                  | 8.3.0        |
| Contenedores      | Docker + docker-compose   | —            |
| Python            | 3.11                      | —            |

---

## Estructura del proyecto

```
Agente Inmobiliario/
│
├── app/
│   ├── orchestrator.py              # MultiSearchResult, natural_language_search()
│   │
│   ├── api/
│   │   ├── main.py                  # FastAPI + TrustedNetworkMiddleware + CORS
│   │   └── routes/
│   │       ├── search.py            # Schemas compartidos (PropertyResultSchema, to_response)
│   │       └── agent_search.py      # POST /api/v1/agent/search  ← único endpoint de búsqueda
│   │
│   ├── services/
│   │   ├── fm_service.py            # FileMaker (solo lectura): search_by_filters()
│   │   ├── dbx_service.py           # Dropbox: get_latest_image_link(), get_folder_link()
│   │   └── agent_service.py         # OpenAI GPT-4o-mini: parse(nl_query) → ParsedQuery
│   │
│   └── ui/
│       └── streamlit_app.py         # text_area + botón → tarjetas de resultados
│
├── config/
│   ├── settings.py                  # Pydantic Settings (singleton lru_cache)
│   └── fm_schema.json               # Campos FM editables (card_field, description_field)
│
├── .env.example
├── requirements.txt
├── Dockerfile
└── docker-compose.yml
```

---

## Flujo de datos

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                               USUARIO                                        │
│                    Abre browser → http://localhost:8501                      │
└──────────────────────────────────┬──────────────────────────────────────────┘
                                   │  HTTP GET :8501
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    DOCKER NETWORK: agente_inmobiliario_net                   │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │              SERVICIO: ui  (contenedor Streamlit :8501)                 │ │
│  │                                                                         │ │
│  │  1. Renderiza text_area + botón "Buscar"                               │ │
│  │  2. Usuario escribe: "Casa en Barcelona con balcón, 3 habitaciones"    │ │
│  │  3. Click en Buscar → Python hace:                                     │ │
│  │                                                                         │ │
│  │     requests.post("http://api:8000/api/v1/agent/search",               │ │
│  │                   json={"query": "..."}, timeout=45)                   │ │
│  │                                  │                                      │ │
│  └──────────────────────────────────┼───────────────────────────────────── ┘ │
│                                     │  HTTP POST (red interna Docker)        │
│                                     │  URL: http://api:8000                  │
│                                     ▼                                        │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │              SERVICIO: api  (contenedor FastAPI :8000)                  │ │
│  │                                                                         │ │
│  │  [main.py]                                                              │ │
│  │  ① TrustedNetworkMiddleware                                            │ │
│  │    → IP del contenedor ui ¿está en ALLOWED_CIDR?                      │ │
│  │    → Dev: 0.0.0.0/0 → permite todo                                    │ │
│  │    → Prod: 192.168.1.0/24 → solo IPs de la red local                 │ │
│  │                                                                         │ │
│  │  ② CORSMiddleware                                                      │ │
│  │    → ¿Origin del request está en ALLOWED_ORIGIN?                      │ │
│  │    → Solo relevante si viene desde browser                            │ │
│  │                                                                         │ │
│  │  ③ Router → agent_search.py → natural_language_search()               │ │
│  │                                                                         │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      orchestrator.py — natural_language_search()             │
│                                                                              │
│  PASO 1 — Interpretar el lenguaje natural                                   │
│  ─────────────────────────────────────────                                  │
│  agent_service.py.parse(nl_query)                                           │
│       │                                                                      │
│       │  HTTPS — api.openai.com                                             │
│       ▼                                                                      │
│  ┌──────────────────────┐                                                   │
│  │  OpenAI GPT-4o-mini  │  Recibe: query + fm_schema.json como contexto    │
│  │  (internet)          │  Devuelve JSON:                                   │
│  └──────────────────────┘  { "ciudad": "Barcelona",                        │
│       │                       "tipo_inmueble": "*Casa*",                    │
│       │                       "descripcion": "*balcón*",                    │
│       │                       "habitaciones": "3",                          │
│       │                       "interpretation": "Buscando..."  }            │
│       ▼                                                                      │
│  ParsedQuery { filters: {...}, interpretation: "..." }                      │
│                                                                              │
│  PASO 2 — Buscar en FileMaker                                               │
│  ────────────────────────────                                               │
│  fm_service.search_by_filters(filters)  [run_in_executor → hilo separado]  │
│       │                                                                      │
│       │  HTTPS — FM_URL  (red local / VPN)                                 │
│       ▼                                                                      │
│  ┌──────────────────────┐                                                   │
│  │  FileMaker Server    │  login() → find([filters]) → logout()            │
│  │  Data API            │  Devuelve: lista de registros que matchean        │
│  └──────────────────────┘                                                   │
│       │                                                                      │
│       │  [ REG-001: {ciudad: Barcelona, tipo: Casa, ...},                  │
│       │    REG-002: {ciudad: Barcelona, tipo: Casa, ...} ]                 │
│       ▼                                                                      │
│  PASO 3 — Enriquecer con Dropbox  (en paralelo por asyncio.gather)         │
│  ─────────────────────────────────────────────────────────────────          │
│                                                                              │
│  Por cada registro FM:                                                      │
│                         │                           │                        │
│                         ▼                           ▼                        │
│              get_latest_image_link()      get_folder_link()                 │
│              [run_in_executor]            [run_in_executor]                 │
│                         │                           │                        │
│                         └───────────┬───────────────┘                       │
│                                     │  HTTPS — api.dropboxapi.com           │
│                                     ▼                                        │
│                         ┌──────────────────────┐                            │
│                         │  Dropbox API v2       │                           │
│                         │  (internet)           │                           │
│                         └──────────────────────┘                            │
│                                     │                                        │
│               files_list_folder(/Inmuebles/REF-001)                        │
│               → elige la imagen con client_modified más reciente            │
│               sharing_create_shared_link_with_settings(archivo) → URL img  │
│               sharing_create_shared_link_with_settings(carpeta) → URL dir  │
│                                                                              │
│  RESULTADO — MultiSearchResult                                              │
│  { query, interpretation, filters_applied, total_found,                     │
│    results: [ { codigo_ref, fm_record, preview_image, dropbox_folder_url}]} │
└──────────────────────────────────────────┬──────────────────────────────────┘
                                           │  JSON response HTTP 200
                                           ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│              SERVICIO: ui — render_results()                                 │
│                                                                              │
│  - Muestra interpretación del agente                                        │
│  - Muestra filtros aplicados (expandible)                                   │
│  - Renderiza N tarjetas en grilla de 3 columnas:                           │
│      st.image(preview_image)        ← URL de Dropbox                       │
│      campos card_field=true         ← desde fm_schema.json                 │
│      <a href=dropbox_folder_url>    ← link carpeta completa                │
└──────────────────────────────────────────┬──────────────────────────────────┘
                                           │  HTML renderizado
                                           ▼
                                      USUARIO ve las tarjetas
```

---

## Instalación y configuración

### 1. Requisitos previos

- Docker Desktop instalado y corriendo.
- Acceso a un servidor FileMaker con Data API habilitada.
- Token de una App de Dropbox.
- API Key de OpenAI.

### 2. Configurar variables de entorno

```bash
cp .env.example .env
```

Editar `.env` con los valores reales:

```env
# FileMaker
FM_URL=https://tu-servidor-filemaker.com
FM_DATABASE=NombreDeTuBaseDeDatos
FM_LAYOUT=NombreDelLayout
FM_USERNAME=usuario_solo_lectura
FM_PASSWORD=password_seguro
FM_REF_FIELD=codigo_ref
FM_DESCRIPTION_FIELD=descripcion

# Dropbox
DROPBOX_TOKEN=sl.xxxxxxxxxxxxxxxxxxxxxx
DROPBOX_BASE_FOLDER=/Inmuebles

# OpenAI
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx

# Seguridad
ALLOWED_CIDR=0.0.0.0/0          # Dev. Prod: 192.168.1.0/24
ALLOWED_ORIGIN=http://localhost:8501

# FastAPI / Streamlit
API_PORT=8000
STREAMLIT_PORT=8501
API_BASE_URL=http://localhost:8000
```

> **Importante:** El usuario de FileMaker debe tener permisos **exclusivamente de lectura**.

### 3. Configurar campos de FileMaker

Editar `config/fm_schema.json` con los nombres reales de los campos del Layout:

```json
{
  "description_field": "descripcion",
  "fields": [
    { "fm_field": "tipo_inmueble", "description": "...", "card_field": true },
    { "fm_field": "ciudad",        "description": "...", "card_field": true },
    ...
  ]
}
```

- `card_field: true` → el campo se muestra en la tarjeta de resultado.
- `card_field: false` → solo se usa como filtro de búsqueda, no se muestra.
- `description_field` → campo donde se buscan términos sin campo FM exacto (texto libre).

---

## Levantar el sistema

```bash
docker-compose up --build        # Primera vez o tras cambios
docker-compose up --build -d     # En segundo plano
docker-compose logs -f           # Ver logs en tiempo real
docker-compose down              # Detener
```

| Servicio       | URL                          |
|----------------|------------------------------|
| API REST       | http://localhost:8000        |
| Docs Swagger   | http://localhost:8000/docs   |
| Interfaz       | http://localhost:8501        |

---

## Uso de la API

### Búsqueda (único endpoint)

```http
POST /api/v1/agent/search
Content-Type: application/json

{ "query": "Casa en Barcelona de madera con balcón luminoso, 3 habitaciones" }
```

**Respuesta exitosa (200):**

```json
{
  "query": "Casa en Barcelona de madera con balcón luminoso, 3 habitaciones",
  "interpretation": "Buscando Casa en Barcelona con materiales de madera, balcón y 3 habitaciones",
  "filters_applied": {
    "tipo_inmueble": "*Casa*",
    "ciudad": "Barcelona",
    "habitaciones": "3",
    "descripcion": "*madera* *luminoso* *balcón*"
  },
  "found": true,
  "total_found": 2,
  "results": [
    {
      "codigo_ref": "REF-2024-001",
      "fm_record": {
        "tipo_inmueble": "Casa",
        "ciudad": "Barcelona",
        "precio": 250000,
        "superficie_m2": 120,
        "habitaciones": 3
      },
      "preview_image": "https://www.dropbox.com/sh/...?raw=1",
      "dropbox_folder_url": "https://www.dropbox.com/sh/...?raw=1"
    }
  ],
  "error": null
}
```

**Respuesta sin resultados:**

```json
{
  "query": "...",
  "found": false,
  "total_found": 0,
  "results": [],
  "error": "No se encontraron inmuebles para '...'."
}
```

### Health check

```http
GET /health
```

---

## Seguridad

| Medida | Detalle |
|--------|---------|
| Red privada | `TrustedNetworkMiddleware` bloquea IPs fuera del CIDR configurado en `ALLOWED_CIDR`. Dev: `0.0.0.0/0`. Prod: `192.168.1.0/24`. |
| FileMaker solo lectura | Solo se llama a `server.find()`. El usuario FM debe tener el privilegio `fmREST` con acceso de solo lectura. |
| CORS restringido | `allow_origins=[ALLOWED_ORIGIN]` — solo el origen de Streamlit puede llamar a la API. |
| Secrets en `.env` | `.env` está en `.gitignore`. Nunca se commitea. |
| Links temporales | Los Shared Links de Dropbox expiran a las **4 horas** (`LINK_EXPIRY_HOURS = 4`). |
| Sin escritura en Dropbox | `dbx_service.py` solo usa `files_list_folder` y `sharing_create_shared_link_with_settings`. |

---

## Decisiones de diseño

**Solo lenguaje natural**
No existe búsqueda por código de referencia. El usuario siempre describe lo que busca en texto libre. GPT-4o-mini traduce esa descripción a filtros FM concretos antes de consultar la base de datos.

**Modelo de datos unificado (`MultiSearchResult`)**
Todas las búsquedas devuelven una lista de `PropertyResult`. No existe un modo de resultado singular — el usuario siempre recibe múltiples opciones.

**Agente NL con schema configurable**
GPT-4o-mini recibe el contenido de `fm_schema.json` en el prompt de sistema. Para adaptar el agente a nuevos campos FM, solo hay que editar ese archivo JSON sin tocar código.

**Imagen más reciente, no la primera**
Dropbox ordena por `client_modified` descendente. Se muestra la foto más nueva para reflejar siempre el estado actual del inmueble.

**FileMaker y Dropbox son bloqueantes → `run_in_executor`**
`python-fmrest` y el SDK de Dropbox no son async-native. Cada llamada se delega a un `ThreadPoolExecutor` para no bloquear el event loop de FastAPI.

**Reintentos con `tenacity`**
3 intentos con backoff exponencial (1s → 8s) en FM y Dropbox. No se duplica esta lógica en el orquestador.

**Shared links de carpeta y de imagen en paralelo**
Por cada registro FM, la imagen más reciente y el link a la carpeta se solicitan simultáneamente con `asyncio.gather()`.

---

## Pendientes

### SSL del servidor FileMaker

En `fm_service.py` la conexión usa `verify_ssl=True` por defecto.

- El servidor tiene certificado **SSL válido** → no requiere cambio.
- El servidor usa certificado **auto-firmado** (on-premise) → cambiar a `verify_ssl=False` o proveer el `.pem`.

### Estructura de carpetas en Dropbox

El sistema asume que la carpeta del inmueble se llama **exactamente igual** al `codigo_ref`:

```
/Inmuebles/
    REF-2024-001/
        frente.jpg
        interior.jpg
```

Si hay subcarpetas adicionales o el nombre difiere del código FM, hay que ajustar `_build_folder_path()` en `dbx_service.py`.
