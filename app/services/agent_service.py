"""
Agent Service — extracción y actualización de filtros FileMaker desde lenguaje natural.

Soporta conversación multi-turno: cada llamada recibe el historial completo
de la conversación y los filtros activos, permitiendo al modelo agregar,
reemplazar o eliminar filtros según el contexto.
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from openai import OpenAI

from config import get_settings

logger = logging.getLogger(__name__)

# Rutas a los archivos de configuración del agente
_SCHEMA_PATH = Path(__file__).parent.parent.parent / "config" / "fm_schema.json"
_PROMPT_PATH = Path(__file__).parent.parent.parent / "config" / "agent_prompt.txt"


@dataclass
class ParsedQuery:
    """Resultado del parsing de una consulta en lenguaje natural."""
    filters: dict[str, str] = field(default_factory=dict)
    description_terms: str = ""
    interpretation: str = ""


def _load_schema() -> dict:
    with open(_SCHEMA_PATH, encoding="utf-8") as f:
        return json.load(f)


def _build_system_prompt(schema: dict) -> str:
    """Construye el prompt de sistema inyectando los campos FM en el template."""
    fields_text = "\n".join(
        f'- fm_field: "{f["fm_field"]}" | {f["description"]}'
        for f in schema["fields"]
        if f["fm_field"] != schema.get("description_field")
    )
    template = _PROMPT_PATH.read_text(encoding="utf-8")
    return template.format(fields_text=fields_text)


class AgentService:
    """
    Servicio de interpretación de lenguaje natural para búsqueda inmobiliaria.
    Soporta conversación multi-turno con historial y filtros acumulados.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._client = OpenAI(api_key=settings.openai_api_key)
        self._schema = _load_schema()
        self._description_field = self._schema.get("description_field", "descripcion")
        self._system_prompt = _build_system_prompt(self._schema)

    def parse_with_history(
        self,
        nl_query: str,
        messages: list[dict],
        current_filters: dict[str, str],
    ) -> ParsedQuery:
        """
        Interpreta una consulta en el contexto de la conversación anterior.

        El modelo recibe el historial completo de turnos anteriores, los filtros
        activos actualmente, y el nuevo mensaje del usuario. Devuelve el conjunto
        COMPLETO de filtros actualizado (puede agregar, reemplazar o eliminar).

        Args:
            nl_query: Nuevo mensaje del usuario.
            messages: Historial [{"role": "user"|"assistant", "content": "..."}].
            current_filters: Filtros FM activos actualmente.
        """
        logger.info(
            "AgentService: turno conversacional — '%s' | filtros activos: %s",
            nl_query,
            list(current_filters.keys()),
        )

        # Base: system prompt con los campos FM
        api_messages: list[dict] = [{"role": "system", "content": self._system_prompt}]

        # Historial de turnos anteriores (user + assistant)
        api_messages.extend(messages)

        # Inyectar estado actual de filtros justo antes del nuevo mensaje
        if current_filters:
            api_messages.append({
                "role": "system",
                "content": (
                    f"Filtros activos en este momento: {json.dumps(current_filters, ensure_ascii=False)}. "
                    "Devuelve el conjunto COMPLETO de filtros actualizado según el nuevo mensaje."
                ),
            })

        api_messages.append({"role": "user", "content": nl_query})

        try:
            response = self._client.chat.completions.create(
                model="gpt-4o-mini",
                response_format={"type": "json_object"},
                temperature=0,
                messages=api_messages,
            )
            raw = response.choices[0].message.content
            data = json.loads(raw)

        except Exception as exc:
            logger.error("AgentService: error llamando a OpenAI — %s", exc)
            # Fallback: conservar filtros actuales y buscar el texto en descripción
            return ParsedQuery(
                filters=current_filters,
                description_terms=nl_query,
                interpretation=f"Búsqueda de texto libre: {nl_query}",
            )

        filters: dict[str, str] = data.get("filters", {})
        description_terms_list: list[str] = data.get("description_terms", [])
        interpretation: str = data.get("interpretation", nl_query)

        # Agregar términos no mapeados al campo descripción de FM
        if description_terms_list:
            terms_joined = " ".join(description_terms_list)
            existing = filters.get(self._description_field, "")
            combined = f"{existing} {terms_joined}".strip()
            filters[self._description_field] = f"*{combined}*"

        logger.info(
            "AgentService: %d filtro(s) — %s",
            len(filters),
            list(filters.keys()),
        )

        return ParsedQuery(
            filters=filters,
            description_terms=" ".join(description_terms_list),
            interpretation=interpretation,
        )
