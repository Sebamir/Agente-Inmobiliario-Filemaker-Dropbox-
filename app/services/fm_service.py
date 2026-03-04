"""
FileMaker Service — cliente de SOLO LECTURA contra FileMaker Data API.

Principios de seguridad:
- El usuario FM configurado en .env debe tener permisos SOLO LECTURA.
- Este servicio NUNCA llama a métodos de escritura (create, edit, delete).
- Toda sesión FM se abre y cierra en el contexto de cada operación.
"""

import asyncio
import logging
from typing import Any

import fmrest
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from config import get_settings

logger = logging.getLogger(__name__)


class FileMakerService:
    """
    Cliente asíncrono para FileMaker Data API (solo lectura).

    FileMaker Data API es bloqueante, por lo que las llamadas se ejecutan
    en un ThreadPoolExecutor para no bloquear el event loop de asyncio.
    """

    def __init__(self) -> None:
        self._settings = get_settings()

    def _build_server(self) -> fmrest.Server:
        """Crea y autentica una instancia del servidor FM."""
        server = fmrest.Server(
            url=self._settings.fm_url,
            user=self._settings.fm_username,
            password=self._settings.fm_password,
            database=self._settings.fm_database,
            layout=self._settings.fm_layout,
            verify_ssl=True,
        )
        server.login()
        return server

    @retry(
        retry=retry_if_exception_type(Exception),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        reraise=True,
    )
    def _find_sync(self, filters: dict[str, str]) -> list[dict[str, Any]]:
        """
        Ejecuta la búsqueda multi-campo en FileMaker (bloqueante).
        Solo usa server.find() — operación de SOLO LECTURA.

        Args:
            filters: Dict de {campo_fm: valor_con_sintaxis_fm}.
                     Ej: {"ciudad": "Barcelona", "tipo_inmueble": "*Casa*"}
        """
        server = self._build_server()

        try:
            # AND: todos los criterios en un único dict de la lista
            find_query = [filters]
            foundset = server.find(query=find_query)

            results = []
            if foundset:
                for record in foundset:
                    results.append(dict(record))

            logger.info(
                "FileMaker: %d registro(s) para filtros %s",
                len(results),
                list(filters.keys()),
            )
            return results

        except Exception as exc:
            logger.error("Error en búsqueda FileMaker: %s", exc)
            raise
        finally:
            # Siempre cerrar la sesión FM para liberar licencias concurrentes
            server.logout()

    async def search_by_filters(self, filters: dict[str, str]) -> list[dict[str, Any]]:
        """
        Busca registros en FileMaker aplicando múltiples filtros (AND).
        Siempre devuelve una lista (0..N registros).

        Args:
            filters: Dict de criterios FM.
                     Búsqueda exacta por ref:  {"codigo_ref": "==REF-2024-001"}
                     Búsqueda multi-campo NL:  {"ciudad": "Barcelona", "tipo_inmueble": "*Casa*"}

        Returns:
            Lista de dicts con los campos del registro FM. Vacía si no hay resultados.
        """
        if not filters:
            logger.warning("FileMaker: search_by_filters llamado sin filtros — abortando")
            return []

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._find_sync, filters)
