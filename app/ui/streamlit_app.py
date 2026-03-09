"""
Interfaz de usuario — Streamlit.

Búsqueda conversacional por lenguaje natural:
  - El usuario describe libremente el inmueble que busca.
  - El agente acumula, reemplaza o elimina filtros entre turnos.
  - Los resultados se presentan como tarjetas con foto, campos clave y link a Dropbox.
  - El historial de la conversación se mantiene en st.session_state (por sesión de browser).
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
.card-ref        { font-size:0.8rem; color:#888; margin-bottom:0.3rem; }
.card-field      { font-size:0.85rem; margin:0.15rem 0; }
.card-label      { font-weight:600; color:#555; }
.badge           { display:inline-block; background:#f0f2f6; border-radius:4px;
                   padding:2px 8px; font-size:0.8rem; margin:2px; }
.interpretation  { background:#e8f4fd; border-left:3px solid #1a73e8;
                   padding:0.6rem 1rem; border-radius:4px; margin-bottom:1rem;
                   font-style:italic; color:#1a1a1a; }
.user-bubble     { background:#f0f2f6; border-radius:12px 12px 2px 12px;
                   padding:0.5rem 0.9rem; margin:0.3rem 0; display:inline-block;
                   max-width:85%; font-size:0.9rem; }
.agent-bubble    { background:#e8f4fd; border-radius:12px 12px 12px 2px;
                   padding:0.5rem 0.9rem; margin:0.3rem 0; display:inline-block;
                   max-width:85%; font-size:0.9rem; color:#1a1a1a; }
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


# ── Session state ─────────────────────────────────────────────────────────────
def _init_session() -> None:
    """Inicializa el estado de la sesión si es la primera vez."""
    if "messages" not in st.session_state:
        st.session_state.messages: list[dict] = []   # historial user/assistant
    if "current_filters" not in st.session_state:
        st.session_state.current_filters: dict = {}  # filtros FM activos
    if "last_results" not in st.session_state:
        st.session_state.last_results: dict | None = None  # última respuesta

def _reset_session() -> None:
    st.session_state.messages = []
    st.session_state.current_filters = {}
    st.session_state.last_results = None


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

    if data.get("filters_applied"):
        with st.expander(f"Filtros activos ({len(data['filters_applied'])})"):
            for k, v in data["filters_applied"].items():
                st.markdown(f'<span class="badge">{k}: {v}</span>', unsafe_allow_html=True)

    st.caption(f"{data.get('total_found', 0)} inmueble(s) encontrado(s)")

    cols = st.columns(3)
    for idx, result in enumerate(data.get("results", [])):
        with cols[idx % 3]:
            render_card(result)


# ── Historial de conversación ─────────────────────────────────────────────────
def render_history() -> None:
    """Muestra el historial de turnos anteriores."""
    if not st.session_state.messages:
        return

    st.markdown("**Conversación**")
    for msg in st.session_state.messages:
        if msg["role"] == "user":
            st.markdown(
                f'<div style="text-align:right"><span class="user-bubble">🧑 {msg["content"]}</span></div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f'<div><span class="agent-bubble">🤖 {msg["content"]}</span></div>',
                unsafe_allow_html=True,
            )
    st.divider()


# ── Lógica de búsqueda ────────────────────────────────────────────────────────
def do_search(query: str) -> None:
    """Envía la consulta al backend con historial y filtros actuales."""
    payload = {
        "query": query,
        "messages": st.session_state.messages,
        "current_filters": st.session_state.current_filters,
    }

    with st.spinner("El agente está buscando..."):
        try:
            response = requests.post(AGENT_URL, json=payload, timeout=45)
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.ConnectionError:
            st.error("No se pudo conectar con el backend.")
            return
        except requests.exceptions.HTTPError as exc:
            st.error(f"Error del servidor: {exc.response.status_code}")
            return
        except Exception as exc:
            st.error(f"Error inesperado: {exc}")
            return

    # Actualizar historial: agregar turno usuario + respuesta del agente
    st.session_state.messages.append({"role": "user", "content": query})
    interpretation = data.get("interpretation") or ""
    if interpretation:
        st.session_state.messages.append({"role": "assistant", "content": interpretation})

    # Actualizar filtros activos con los que devolvió el agente
    if data.get("filters_applied"):
        st.session_state.current_filters = data["filters_applied"]

    st.session_state.last_results = data


# ── Layout principal ──────────────────────────────────────────────────────────
_init_session()

col_title, col_reset = st.columns([8, 1])
with col_title:
    st.title("Agente de Búsqueda Inmobiliaria")
    st.caption("Describí el inmueble que buscás. Podés ir refinando la búsqueda en cada mensaje.")
with col_reset:
    st.write("")  # espaciado vertical
    if st.button("🔄 Nueva", help="Reiniciar conversación", use_container_width=True):
        _reset_session()
        st.rerun()

st.divider()

# Historial de la conversación actual
render_history()

# Input de búsqueda
nl_query = st.text_area(
    "¿Qué inmueble buscás?",
    placeholder="Ej: Casa en Barcelona con balcón y 3 habitaciones",
    height=90,
    key="query_input",
)

if st.button("Buscar", type="primary", use_container_width=False):
    if nl_query.strip():
        do_search(nl_query.strip())
    else:
        st.warning("Describí qué tipo de inmueble buscás.")

# Resultados de la última búsqueda
if st.session_state.last_results:
    st.divider()
    render_results(st.session_state.last_results)

# ── Footer ────────────────────────────────────────────────────────────────────
st.divider()
st.caption("Agente Inmobiliario v0.3 — FileMaker + Dropbox + GPT-4o-mini")
