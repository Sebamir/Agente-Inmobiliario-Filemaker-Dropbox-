"""
FastAPI — punto de entrada de la API del Agente Inmobiliario.
"""

import ipaddress
import logging
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.api.routes import agent_search
from config import get_settings

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s — %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

settings = get_settings()


# ── Middleware: red privada ───────────────────────────────────────────────────

class TrustedNetworkMiddleware(BaseHTTPMiddleware):
    """
    Restringe el acceso a IPs dentro del CIDR configurado en ALLOWED_CIDR.

    Dev:  ALLOWED_CIDR=0.0.0.0/0   → permite todo
    Prod: ALLOWED_CIDR=192.168.1.0/24 → solo red interna
    """

    def __init__(self, app, allowed_cidr: str) -> None:
        super().__init__(app)
        self._network = ipaddress.ip_network(allowed_cidr, strict=False)

    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host if request.client else "0.0.0.0"
        try:
            if ipaddress.ip_address(client_ip) not in self._network:
                logger.warning("Acceso denegado desde IP: %s", client_ip)
                return JSONResponse(
                    {"detail": "Acceso no autorizado. Red no permitida."},
                    status_code=403,
                )
        except ValueError:
            logger.error("IP inválida: %s", client_ip)
            return JSONResponse({"detail": "IP inválida."}, status_code=400)

        return await call_next(request)


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Agente Inmobiliario API",
    description="API de búsqueda de inmuebles integrada con FileMaker y Dropbox.",
    version="0.2.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# El orden importa: TrustedNetwork se evalúa ANTES que CORS
app.add_middleware(TrustedNetworkMiddleware, allowed_cidr=settings.allowed_cidr)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.allowed_origin],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(agent_search.router, prefix="/api/v1")


@app.get("/", tags=["Root"])
async def root() -> dict[str, str]:
    return {"message": "Agente Inmobiliario API v0.2 — /docs para documentación"}


@app.get("/health", tags=["Root"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
