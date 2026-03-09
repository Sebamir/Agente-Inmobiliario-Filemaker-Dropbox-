"""
Rutas de búsqueda por lenguaje natural — FastAPI.
"""

import logging

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.orchestrator import RealEstateOrchestrator
from app.api.routes.search import SearchResponseSchema, to_response

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/agent", tags=["Búsqueda Inteligente"])

_orchestrator = RealEstateOrchestrator()


class ConversationMessage(BaseModel):
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str


class NLSearchRequest(BaseModel):
    query: str = Field(
        ...,
        min_length=2,
        max_length=500,
        description="Nuevo mensaje del usuario",
        examples=["Necesito una casa en Barcelona con balcón"],
    )
    messages: list[ConversationMessage] = Field(
        default_factory=list,
        description="Historial de turnos anteriores de la conversación",
    )
    current_filters: dict[str, str] = Field(
        default_factory=dict,
        description="Filtros FM activos en este momento",
    )


@router.post(
    "/search",
    response_model=SearchResponseSchema,
    summary="Búsqueda conversacional de inmuebles",
)
async def natural_language_search(body: NLSearchRequest) -> SearchResponseSchema:
    """
    Interpreta el nuevo mensaje del usuario en el contexto de la conversación
    y busca inmuebles en FileMaker con los filtros actualizados.

    - El agente acumula, reemplaza o elimina filtros según el contexto.
    - Devuelve resultados con foto más reciente y link a carpeta Dropbox.
    """
    history = [{"role": m.role, "content": m.content} for m in body.messages]
    result = await _orchestrator.natural_language_search(
        nl_query=body.query,
        messages=history,
        current_filters=body.current_filters,
    )
    return to_response(result)
