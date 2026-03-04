"""
Interfaz de usuario — Streamlit.

Búsqueda única por lenguaje natural:
  - El usuario describe libremente el inmueble que busca.
  - GPT-4o-mini extrae los filtros y los aplica contra FileMaker.
  - Los resultados se presentan como tarjetas con foto, campos clave y link a Dropbox.
"""

import json
from pathlib import Path

import requests
import streamlit as st

from config import get_settings

settings = get_settings()
AGENT_URL   = f"{settings.api_base_url}/api/v1/agent/search"
SCHEMA_PATH = Path(__file__).parent.parent.parent / "config" / "fm_schema.json"

# ── Configuración de página ───────────────────────────────────────────────────
st.set_page_config(
    page_title="Agente Inmobiliario",
    page_icon="🏠",
    layout="wide",
)

# ── Estilos ───────────────────────────────────────────────────────────────────
st.markdown("""
<style>
.card-ref   { font-size:0.8rem; color:#888; margin-bottom:0.3rem; }
.card-field { font-size:0.85rem; margin:0.15rem 0; }
.card-label { font-weight:600; color:#555; }
.badge      { display:inline-block; background:#f0f2f6; border-radius:4px;
              padding:2px 8px; font-size:0.8rem; margin:2px; }
.interpretation { background:#e8f4fd; border-left:3px solid #1a73e8;
                  padding:0.6rem 1rem; border-radius:4px; margin-bottom:1rem;
                  font-style:italic; color:#1a1a1a; }
</style>
""", unsafe_allow_html=True)


# ── Schema FM ─────────────────────────────────────────────────────────────────
@st.cache_data
def load_card_fields() -> list[dict]:
    try:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        return [f for f in schema.get("fields", []) if f.get("card_field")]
    except Exception:
        return []

CARD_FIELDS = load_card_fields()


# ── Componente tarjeta ────────────────────────────────────────────────────────
def render_card(result: dict) -> None:
    fm = result.get("fm_record", {})

    if result.get("preview_image"):
        st.image(result["preview_image"], use_container_width=True)
    else:
        st.markdown("*Sin imagen disponible*")

    st.markdown(
        f'<p class="card-ref">{result.get("codigo_ref", "")}</p>',
        unsafe_allow_html=True,
    )

    for field_def in CARD_FIELDS:
        value = fm.get(field_def["fm_field"])
        if value:
            label = field_def.get("display_name", field_def["fm_field"])
            st.markdown(
                f'<p class="card-field"><span class="card-label">{label}:</span> {value}</p>',
                unsafe_allow_html=True,
            )

    folder_url = result.get("dropbox_folder_url")
    if folder_url:
        st.markdown(
            f'<a href="{folder_url}" target="_blank">📁 Ver carpeta en Dropbox</a>',
            unsafe_allow_html=True,
        )

    st.divider()


def render_results(data: dict) -> None:
    if not data.get("found"):
        st.warning(data.get("error") or "No se encontraron resultados.")
        return

    if data.get("interpretation"):
        st.markdown(
            f'<div class="interpretation">🤖 {data["interpretation"]}</div>',
            unsafe_allow_html=True,
        )

    if data.get("filters_applied"):
        with st.expander(f"Filtros aplicados ({len(data['filters_applied'])})"):
            for k, v in data["filters_applied"].items():
                st.markdown(f'<span class="badge">{k}: {v}</span>', unsafe_allow_html=True)

    st.caption(f"{data.get('total_found', 0)} inmueble(s) encontrado(s)")

    cols = st.columns(3)
    for idx, result in enumerate(data.get("results", [])):
        with cols[idx % 3]:
            render_card(result)

    if data.get("error"):
        st.warning(f"Aviso: {data['error']}")


# ── Header ────────────────────────────────────────────────────────────────────
st.title("Agente de Búsqueda Inmobiliaria")
st.caption("Describí el inmueble que buscás y el agente encontrará las mejores opciones.")
st.divider()

# ── Búsqueda ──────────────────────────────────────────────────────────────────
nl_query = st.text_area(
    "¿Qué inmueble buscás?",
    placeholder="Ej: Necesito una casa en Barcelona de madera con balcón luminoso, 3 habitaciones y jardín",
    height=110,
)

if st.button("Buscar", type="primary", use_container_width=False):
    if nl_query.strip():
        with st.spinner("El agente está buscando..."):
            try:
                response = requests.post(
                    AGENT_URL,
                    json={"query": nl_query.strip()},
                    timeout=45,
                )
                response.raise_for_status()
                render_results(response.json())
            except requests.exceptions.ConnectionError:
                st.error("No se pudo conectar con el backend. Verificar que FastAPI esté corriendo.")
            except requests.exceptions.HTTPError as exc:
                st.error(f"Error del servidor: {exc.response.status_code}")
            except Exception as exc:
                st.error(f"Error inesperado: {exc}")
    else:
        st.warning("Describí qué tipo de inmueble buscás.")

# ── Footer ────────────────────────────────────────────────────────────────────
st.divider()
st.caption("Agente Inmobiliario v0.2 — FileMaker + Dropbox + GPT-4o-mini")
