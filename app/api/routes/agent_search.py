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


class NLSearchRequest(BaseModel):
    query: str = Field(
        ...,
        min_length=5,
        max_length=500,
        description="Consulta en lenguaje natural",
        examples=["Necesito una casa en Barcelona de madera con balcón luminoso"],
    )


@router.post(
    "/search",
    response_model=SearchResponseSchema,
    summary="Búsqueda de inmuebles por lenguaje natural",
)
async def natural_language_search(body: NLSearchRequest) -> SearchResponseSchema:
    """
    Interpreta una consulta libre y busca inmuebles en FileMaker.

    - GPT-4o-mini extrae filtros estructurados de la consulta.
    - Términos sin campo FM directo se buscan en el campo descripción.
    - Devuelve lista de resultados con foto más reciente y link a carpeta Dropbox.
    """
    result = await _orchestrator.natural_language_search(body.query)
    return to_response(result)
