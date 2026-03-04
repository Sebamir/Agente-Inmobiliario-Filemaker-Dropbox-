# Agente de Búsqueda Inmobiliaria

Sistema multiusuario para búsqueda de inmuebles que integra **FileMaker** (fuente de datos) con **Dropbox** (almacenamiento de imágenes), expuesto mediante una API REST (FastAPI) y una interfaz web (Streamlit).

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
10. [Preguntas pendientes para continuar](#preguntas-pendientes-para-continuar)

---

## Arquitectura

```
┌─────────────────────────────────────────────────────────┐
│                     Docker Network                       │
│                                                         │
│  ┌──────────────┐   HTTP    ┌──────────────────────┐   │
│  │  Streamlit   │ ────────► │   FastAPI (uvicorn)  │   │
│  │  :8501       │           │   :8000              │   │
│  └──────────────┘           └──────────┬───────────┘   │
│                                        │                │
│                              ┌─────────▼──────────┐    │
│                              │   Orquestador       │    │
│                              │   (async)           │    │
│                              └──────┬──────┬───────┘    │
│                                     │      │             │
└─────────────────────────────────────┼──────┼────────────┘
                                      │      │
                    ┌─────────────────▼─┐  ┌─▼──────────────────┐
                    │   FileMaker       │  │   Dropbox API v2    │
                    │   Data API        │  │   (shared links)    │
                    │   (solo lectura)  │  └─────────────────────┘
                    └───────────────────┘
```

---

## Stack tecnológico

| Capa          | Tecnología                    | Versión  |
|---------------|-------------------------------|----------|
| API Backend   | FastAPI + Uvicorn             | 0.111 / 0.29 |
| FileMaker     | python-fmrest                 | 1.7.0    |
| Dropbox       | dropbox SDK                   | 12.0.2   |
| Interfaz      | Streamlit                     | 1.35.0   |
| Configuración | pydantic-settings             | 2.3.0    |
| Reintentos    | tenacity                      | 8.3.0    |
| Contenedores  | Docker + docker-compose       | —        |
| Python        | 3.11                          | —        |

---

## Estructura del proyecto

```
Agente Inmobiliario/
│
├── app/
│   ├── __init__.py
│   ├── orchestrator.py           # Orquestador asíncrono principal
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── main.py               # Entrada FastAPI (CORS, routers, logging)
│   │   └── routes/
│   │       ├── __init__.py
│   │       └── search.py         # GET /api/v1/search/?ref=...
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── fm_service.py         # Cliente FileMaker (solo lectura)
│   │   └── dbx_service.py        # Cliente Dropbox (imágenes + links)
│   │
│   └── ui/
│       ├── __init__.py
│       └── streamlit_app.py      # Interfaz de usuario web
│
├── config/
│   ├── __init__.py
│   └── settings.py               # Pydantic Settings (singleton con lru_cache)
│
├── .env.example                  # Template de variables de entorno
├── .gitignore
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── README.md
```

---

## Flujo de datos

```
Usuario ingresa código (ej: REF-2024-001)
           │
           ▼
  Streamlit → POST /api/v1/search/?ref=REF-2024-001
           │
           ▼
  Orquestador (orchestrator.py)
     │
     ├── 1. FileMakerService.get_by_ref("REF-2024-001")
     │        └── FileMaker Data API (find, solo lectura)
     │        └── Retorna: dict con campos del registro
     │
     ├── 2. DropboxService.list_images("REF-2024-001")
     │        └── Lista archivos en /Inmuebles/REF-2024-001/
     │        └── Filtra por extensión: .jpg .jpeg .png .webp .gif .heic
     │
     └── 3. asyncio.gather() → shared links temporales (4 horas)
              └── Hasta 10 imágenes en paralelo
              └── Retorna URL de previsualización directa
           │
           ▼
  SearchResult → JSON → Streamlit → Galería de imágenes
```

---

## Instalación y configuración

### 1. Requisitos previos

- Docker Desktop instalado y corriendo.
- Acceso a un servidor FileMaker con Data API habilitada.
- Token de acceso a una App de Dropbox.

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

# Dropbox
DROPBOX_TOKEN=sl.xxxxxxxxxxxxxxxxxxxxxx
DROPBOX_BASE_FOLDER=/Inmuebles

# FastAPI
API_PORT=8000

# Streamlit
STREAMLIT_PORT=8501
API_BASE_URL=http://localhost:8000
```

> **Importante:** El usuario de FileMaker debe tener permisos **exclusivamente de lectura**. Ver sección [Seguridad](#seguridad).

---

## Levantar el sistema

```bash
# Construir imágenes y levantar servicios
docker-compose up --build

# En segundo plano
docker-compose up --build -d

# Ver logs en tiempo real
docker-compose logs -f

# Detener
docker-compose down
```

| Servicio   | URL                     |
|------------|-------------------------|
| API REST   | http://localhost:8000   |
| Docs Swagger | http://localhost:8000/docs |
| Interfaz   | http://localhost:8501   |

---

## Uso de la API

### Buscar inmueble

```http
GET /api/v1/search/?ref=REF-2024-001
```

**Respuesta exitosa (200):**

```json
{
  "codigo_ref": "REF-2024-001",
  "found": true,
  "fm_record": {
    "codigo_ref": "REF-2024-001",
    "direccion": "Av. Corrientes 1234",
    "precio": 250000,
    "...": "..."
  },
  "images": [
    {
      "name": "frente.jpg",
      "path": "/Inmuebles/REF-2024-001/frente.jpg",
      "preview_url": "https://www.dropbox.com/...",
      "size": 204800
    }
  ],
  "total_images": 1,
  "error": null
}
```

**Respuesta no encontrado:**

```json
{
  "codigo_ref": "REF-9999",
  "found": false,
  "fm_record": {},
  "images": [],
  "total_images": 0,
  "error": "No se encontró ningún inmueble con referencia 'REF-9999'."
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
| FileMaker solo lectura | El servicio únicamente llama a `server.find()`. El usuario FM debe tener el privilegio `fmREST` con acceso de solo lectura al layout. |
| Secrets en `.env` | El archivo `.env` está en `.gitignore`. Nunca se commitea al repositorio. |
| CORS restringido | En producción, reemplazar `allow_origins=["*"]` en `main.py` por el origen real de Streamlit. |
| Links temporales | Los Shared Links de Dropbox expiran a las 4 horas (`LINK_EXPIRY_HOURS = 4`). |
| Sin escritura en Dropbox | `dbx_service.py` solo usa `files_list_folder` y `sharing_create_shared_link_with_settings`. |

---

## Decisiones de diseño

**FileMaker es bloqueante → `run_in_executor`**
La librería `python-fmrest` no es async-native. Cada llamada se delega a un `ThreadPoolExecutor` para no bloquear el event loop de FastAPI.

**Reintentos con `tenacity`**
Las llamadas a FileMaker y Dropbox tienen 3 intentos automáticos con backoff exponencial (1s → 8s máx). Esto cubre cortes transitorios de red sin necesidad de lógica manual.

**Shared links en paralelo**
Los links de las imágenes se generan con `asyncio.gather()`, por lo que 10 imágenes se procesan al mismo tiempo en lugar de secuencialmente.

**Singleton de configuración**
`get_settings()` usa `@lru_cache`, garantizando que el archivo `.env` se lea una sola vez en todo el ciclo de vida del proceso.

---

## Preguntas pendientes para continuar

Las siguientes decisiones afectan el desarrollo de las próximas funcionalidades. Se requiere confirmación antes de avanzar.

---

### 1. SSL del servidor FileMaker

> En `fm_service.py`, la conexión usa `verify_ssl=True` por defecto.

- **a)** El servidor FileMaker tiene un certificado SSL **válido y firmado** por una CA reconocida → no se necesita cambio.
- **b)** El servidor usa un certificado **auto-firmado** (interno, on-premise) → hay que cambiar a `verify_ssl=False` o proveer el `.pem` del certificado.

---

### 2. Estructura de carpetas en Dropbox

> El sistema asume que la carpeta del inmueble se llama **exactamente igual** al `codigo_ref` del registro FM.

```
/Inmuebles/
    REF-2024-001/    ← ¿así de directo?
        frente.jpg
        interior.jpg
    REF-2024-002/
        ...
```

- **a)** Sí, la carpeta se llama igual al código de referencia.
- **b)** Hay subcarpetas adicionales (ej: `/Inmuebles/2024/REF-2024-001/` o `/Inmuebles/REF-2024-001/Fotos/`).
- **c)** El nombre de carpeta es diferente al código FM (necesito saber la regla de mapeo).

---

### 3. Autenticación de la API

> Actualmente la API es abierta dentro de la red Docker. ¿Quién accede al sistema?

- **a)** Solo usuarios internos en red local → sin autenticación por ahora.
- **b)** Acceso desde fuera de la red local → agregar **API Key** en header (`X-API-Key`).
- **c)** Usuarios identificados con login → agregar **JWT** (usuario + contraseña).

---

### 4. Campos a mostrar de FileMaker

> El `fm_record` devuelve **todos** los campos del Layout tal como los retorna FM.

- **a)** Mostrar todos los campos disponibles (comportamiento actual).
- **b)** Definir una lista fija de campos relevantes (ej: dirección, precio, superficie, ambientes) y descartar el resto.

---

### 5. Comportamiento multiusuario

> ¿Cuántos usuarios concurrentes se esperan?

- **a)** Pocos usuarios (< 10 simultáneos) → la configuración actual es suficiente.
- **b)** Carga moderada (10-50) → evaluar pool de conexiones FM y caché de resultados.
- **c)** Alta carga → necesitamos Redis para caché y múltiples workers de uvicorn.
