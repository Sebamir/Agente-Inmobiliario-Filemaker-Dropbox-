"""
Agent Service — extracción de filtros FileMaker desde lenguaje natural.

Usa OpenAI GPT-4o-mini para interpretar una consulta libre del usuario
y mapearla a campos concretos del Layout de FileMaker definidos en
config/fm_schema.json.
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from openai import OpenAI

from config import get_settings

logger = logging.getLogger(__name__)

# Ruta al schema de campos FM
_SCHEMA_PATH = Path(__file__).parent.parent.parent / "config" / "fm_schema.json"


@dataclass
class ParsedQuery:
    """Resultado del parsing de una consulta en lenguaje natural."""
    filters: dict[str, str] = field(default_factory=dict)
    # Términos que no mapearon a ningún campo → se buscan en el campo descripción
    description_terms: str = ""
    # Texto explicativo de lo que entendió el agente (para mostrar al usuario)
    interpretation: str = ""


def _load_schema() -> dict:
    """Carga el schema de campos FM desde disco."""
    with open(_SCHEMA_PATH, encoding="utf-8") as f:
        return json.load(f)


def _build_system_prompt(schema: dict) -> str:
    """Construye el prompt de sistema con el schema FM."""
    fields_text = "\n".join(
        f'- fm_field: "{f["fm_field"]}" | {f["description"]}'
        for f in schema["fields"]
        if f["fm_field"] != schema.get("description_field")
    )
    description_field = schema.get("description_field", "descripcion")

    return f"""Eres un asistente especializado en búsqueda inmobiliaria.
Tu tarea es analizar la consulta del usuario y extraer filtros de búsqueda
mapeados a los campos de la base de datos FileMaker.

Campos disponibles en FileMaker:
{fields_text}

Reglas de extracción:
1. Mapea cada concepto del usuario al campo FM más apropiado.
2. Para texto, usa comodines FileMaker: *valor* para búsqueda parcial, ==valor para exacta.
3. Para rangos numéricos (precio, superficie), usa la sintaxis FM: >100 <500 o ..500 (menor o igual).
4. Los términos que NO puedan mapearse a ningún campo van al array "description_terms" como lista de palabras clave.
5. "interpretation" debe ser una frase corta en español explicando qué entendiste.

Responde ÚNICAMENTE con un JSON válido con esta estructura exacta:
{{
  "filters": {{
    "nombre_campo_fm": "valor_con_sintaxis_fm"
  }},
  "description_terms": ["término1", "término2"],
  "interpretation": "Buscando [tipo] en [ciudad] con [características]..."
}}

Si no hay filtros aplicables, devuelve filters vacío y pon los términos en description_terms."""


class AgentService:
    """
    Servicio de interpretación de lenguaje natural para búsqueda inmobiliaria.
    Usa GPT-4o-mini para mapear consultas libres a filtros FileMaker.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._client = OpenAI(api_key=settings.openai_api_key)
        self._schema = _load_schema()
        self._description_field = self._schema.get("description_field", "descripcion")
        self._system_prompt = _build_system_prompt(self._schema)

    def parse(self, nl_query: str) -> ParsedQuery:
        """
        Interpreta una consulta en lenguaje natural y devuelve filtros FM estructurados.

        Args:
            nl_query: Consulta libre del usuario (ej: "casa en Barcelona con balcón").

        Returns:
            ParsedQuery con filters para FM, description_terms e interpretation.
        """
        logger.info("AgentService: parseando consulta '%s'", nl_query)

        try:
            response = self._client.chat.completions.create(
                model="gpt-4o-mini",
                response_format={"type": "json_object"},
                temperature=0,  # Determinismo para extracción estructurada
                messages=[
                    {"role": "system", "content": self._system_prompt},
                    {"role": "user", "content": nl_query},
                ],
            )

            raw = response.choices[0].message.content
            data = json.loads(raw)

        except Exception as exc:
            logger.error("AgentService: error llamando a OpenAI — %s", exc)
            # Fallback: buscar todo el texto en el campo descripción
            return ParsedQuery(
                filters={},
                description_terms=nl_query,
                interpretation=f"Búsqueda de texto libre: {nl_query}",
            )

        filters: dict[str, str] = data.get("filters", {})
        description_terms_list: list[str] = data.get("description_terms", [])
        interpretation: str = data.get("interpretation", nl_query)

        # Agregar términos no mapeados al campo descripción de FM
        if description_terms_list:
            terms_joined = " ".join(description_terms_list)
            # Si ya hay un filtro de descripción, combinarlo
            existing = filters.get(self._description_field, "")
            combined = f"{existing} {terms_joined}".strip()
            filters[self._description_field] = f"*{combined}*"

        logger.info(
            "AgentService: %d filtro(s) extraídos — %s",
            len(filters),
            list(filters.keys()),
        )

        return ParsedQuery(
            filters=filters,
            description_terms=" ".join(description_terms_list),
            interpretation=interpretation,
        )
