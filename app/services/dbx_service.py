"""
Dropbox Service — gestión de carpetas y generación de Shared Links temporales.

Responsabilidades:
- Localizar la carpeta de un inmueble a partir de su código de referencia.
- Listar las imágenes disponibles en esa carpeta.
- Generar un Shared Link a la imagen más reciente (por fecha de modificación).
- Generar un Shared Link a la carpeta completa para navegación profunda.
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Any

import dropbox
from dropbox.exceptions import ApiError, AuthError
from dropbox.files import ListFolderError
from dropbox.sharing import RequestedVisibility, SharedLinkSettings
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from config import get_settings

logger = logging.getLogger(__name__)

# Extensiones de imagen soportadas para previsualización
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic"}

# Duración del shared link temporal (en horas)
LINK_EXPIRY_HOURS = 4


class DropboxService:
    """
    Cliente asíncrono para Dropbox API v2.

    La API de Dropbox es bloqueante; las operaciones se delegan
    a un ThreadPoolExecutor para mantener el event loop libre.
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        self._client: dropbox.Dropbox | None = None

    def _get_client(self) -> dropbox.Dropbox:
        """Retorna (o crea) el cliente Dropbox reutilizable."""
        if self._client is None:
            try:
                self._client = dropbox.Dropbox(self._settings.dropbox_token)
                # Verificar token al inicializar
                self._client.users_get_current_account()
                logger.info("Dropbox: cliente autenticado correctamente")
            except AuthError as exc:
                logger.error("Dropbox: token inválido — %s", exc)
                raise
        return self._client

    def _build_folder_path(self, codigo_ref: str) -> str:
        """Construye la ruta completa de la carpeta del inmueble en Dropbox."""
        base = self._settings.dropbox_base_folder.rstrip("/")
        return f"{base}/{codigo_ref}"

    @retry(
        retry=retry_if_exception_type(Exception),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        reraise=True,
    )
    def _list_images_sync(self, folder_path: str) -> list[dict[str, Any]]:
        """Lista las imágenes de una carpeta (bloqueante)."""
        client = self._get_client()
        images = []

        try:
            result = client.files_list_folder(folder_path)
            entries = result.entries

            # Manejar paginación si hay muchos archivos
            while result.has_more:
                result = client.files_list_folder_continue(result.cursor)
                entries.extend(result.entries)

            for entry in entries:
                if not isinstance(entry, dropbox.files.FileMetadata):
                    continue
                ext = "." + entry.name.rsplit(".", 1)[-1].lower() if "." in entry.name else ""
                if ext in IMAGE_EXTENSIONS:
                    images.append({
                        "name": entry.name,
                        "path": entry.path_lower,
                        "size": entry.size,
                        "modified": entry.client_modified.isoformat() if entry.client_modified else None,
                    })

            logger.info("Dropbox: %d imagen(es) en '%s'", len(images), folder_path)
            return images

        except ApiError as exc:
            if isinstance(exc.error, ListFolderError) and exc.error.is_path():
                logger.warning("Dropbox: carpeta no encontrada — '%s'", folder_path)
                return []
            logger.error("Dropbox: error listando carpeta '%s' — %s", folder_path, exc)
            raise

    def _create_shared_link_sync(self, path: str) -> str | None:
        """
        Genera un shared link temporal para un archivo o carpeta (bloqueante).
        Expira en LINK_EXPIRY_HOURS horas.
        """
        client = self._get_client()
        expiry = datetime.now(timezone.utc) + timedelta(hours=LINK_EXPIRY_HOURS)

        settings = SharedLinkSettings(
            requested_visibility=RequestedVisibility.team_only,
            expires=expiry,
        )

        try:
            link_metadata = client.sharing_create_shared_link_with_settings(
                path, settings=settings
            )
            url = link_metadata.url.replace("?dl=0", "?raw=1")
            logger.info("Dropbox: shared link generado para '%s'", path)
            return url

        except ApiError as exc:
            if exc.error.is_shared_link_already_exists():
                existing = exc.error.get_shared_link_already_exists()
                if existing and existing.metadata:
                    url = existing.metadata.url.replace("?dl=0", "?raw=1")
                    logger.info("Dropbox: link existente reutilizado para '%s'", path)
                    return url
            logger.error("Dropbox: no se pudo crear shared link para '%s' — %s", path, exc)
            return None

    # ─── API pública asíncrona ───────────────────────────────────────────────

    async def list_images(self, codigo_ref: str) -> list[dict[str, Any]]:
        """Lista las imágenes de la carpeta del inmueble."""
        folder_path = self._build_folder_path(codigo_ref)
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._list_images_sync, folder_path)

    async def get_preview_link(self, file_path: str) -> str | None:
        """Genera un shared link temporal para un archivo."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._create_shared_link_sync, file_path)

    async def get_latest_image_link(self, codigo_ref: str) -> str | None:
        """
        Devuelve el shared link de la imagen más reciente del inmueble
        (ordenada por client_modified descendente).
        """
        images = await self.list_images(codigo_ref)
        if not images:
            return None
        latest = max(images, key=lambda img: img.get("modified") or "")
        return await self.get_preview_link(latest["path"])

    async def get_folder_link(self, codigo_ref: str) -> str | None:
        """
        Genera un shared link apuntando a la carpeta completa del inmueble en Dropbox.
        Permite al usuario explorar todas las imágenes directamente.
        """
        folder_path = self._build_folder_path(codigo_ref)
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._create_shared_link_sync, folder_path)
