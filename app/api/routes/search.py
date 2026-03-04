"""
Schemas de respuesta compartidos por las rutas de búsqueda.
"""

from typing import Any

from pydantic import BaseModel, Field

from app.orchestrator import MultiSearchResult


class PropertyResultSchema(BaseModel):
    codigo_ref: str
    fm_record: dict[str, Any] = Field(default_factory=dict)
    preview_image: str | None = None
    dropbox_folder_url: str | None = None


class SearchResponseSchema(BaseModel):
    query: str
    interpretation: str = ""
    filters_applied: dict[str, str] = Field(default_factory=dict)
    found: bool
    total_found: int = 0
    results: list[PropertyResultSchema] = Field(default_factory=list)
    error: str | None = None


def to_response(result: MultiSearchResult) -> SearchResponseSchema:
    """Convierte MultiSearchResult al schema de respuesta HTTP."""
    return SearchResponseSchema(
        query=result.query,
        interpretation=result.interpretation,
        filters_applied=result.filters_applied,
        found=result.found,
        total_found=result.total_found,
        results=[
            PropertyResultSchema(
                codigo_ref=r.codigo_ref,
                fm_record=r.fm_record,
                preview_image=r.preview_image,
                dropbox_folder_url=r.dropbox_folder_url,
            )
            for r in result.results
        ],
        error=result.error,
    )
