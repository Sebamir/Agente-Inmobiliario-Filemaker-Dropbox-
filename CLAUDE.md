# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

**Run locally (without Docker):**
```bash
# Activate virtualenv (Windows)
venv\Scripts\activate

# FastAPI backend
uvicorn app.api.main:app --host 0.0.0.0 --port 8000 --reload

# Streamlit UI (separate terminal)
streamlit run app/ui/streamlit_app.py --server.port 8501
```

**Run with Docker:**
```bash
docker-compose up --build          # Build and start both services
docker-compose up --build -d       # Detached mode
docker-compose logs -f api         # Tail API logs
docker-compose logs -f ui          # Tail UI logs
docker-compose down                # Stop all services
```

**Install dependencies:**
```bash
pip install -r requirements.txt
```

## Architecture

Two Docker services share a network (`agente_inmobiliario_net`):
- **`api`** — FastAPI on port 8000, reads `.env` directly
- **`ui`** — Streamlit on port 8501, calls `api` via `http://api:8000` inside Docker, or `API_BASE_URL` env var locally

### Request flow

```
Streamlit → GET /api/v1/search/?ref={codigo_ref}
              └─ RealEstateOrchestrator.search()
                    ├─ FileMakerService.get_by_ref()     # run_in_executor (blocking SDK)
                    └─ DropboxService.list_images()      # run_in_executor (blocking SDK)
                          └─ asyncio.gather() → shared links per image (parallel)
```

### Key architectural constraints

**FileMaker SDK is synchronous.** `python-fmrest` blocks the thread. All FM calls go through `asyncio.get_running_loop().run_in_executor(None, ...)` in both `fm_service.py` and `dbx_service.py`. Never call the FM or Dropbox SDKs directly from an `async def` without `run_in_executor`.

**FileMaker sessions must be closed.** `server.login()` consumes a concurrent connection license. Every `_search_sync` call opens and closes its own session in a `try/finally` block.

**`codigo_ref` is the single join key.** The alphanumeric code (e.g. `REF-2024-001`) stored in the FM field defined by `FM_REF_FIELD` must match the Dropbox folder name under `DROPBOX_BASE_FOLDER`. No other mapping exists.

### Configuration

`config/settings.py` uses `pydantic-settings` with `@lru_cache` — settings are read from `.env` once and reused as a singleton. Access anywhere via `from config import get_settings; s = get_settings()`.

### Resilience

Both services wrap their sync calls with `@retry` from `tenacity` (3 attempts, exponential backoff 1–8s). This is already applied at the `_*_sync` method level — do not add additional retry logic at the orchestrator or route layer.

### Limits

- Max images processed per search: `MAX_IMAGES = 10` in `orchestrator.py`
- Shared link TTL: `LINK_EXPIRY_HOURS = 4` in `dbx_service.py`
- If a Dropbox shared link already exists for a file, the existing link is reused (handled in `_create_shared_link_sync`)

## Environment variables

Copy `.env.example` → `.env`. Required keys: `FM_URL`, `FM_DATABASE`, `FM_LAYOUT`, `FM_USERNAME`, `FM_PASSWORD`, `FM_REF_FIELD`, `DROPBOX_TOKEN`, `DROPBOX_BASE_FOLDER`.

The FM user must be read-only at the FileMaker privilege set level — the code itself does not enforce this beyond never calling write methods.
