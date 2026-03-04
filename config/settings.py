from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    """
    Configuración central del proyecto.
    Lee automáticamente desde variables de entorno o archivo .env
    """
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # --- FileMaker ---
    fm_url: str
    fm_database: str
    fm_layout: str
    fm_username: str
    fm_password: str
    fm_ref_field: str = "codigo_ref"

    # --- Dropbox ---
    dropbox_token: str
    dropbox_base_folder: str = "/Inmuebles"

    # --- FastAPI ---
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_debug: bool = False

    # --- Agente NL (OpenAI) ---
    openai_api_key: str = ""
    fm_description_field: str = "descripcion"  # Campo FM para texto libre no mapeado

    # --- Seguridad / Red ---
    allowed_cidr: str = "0.0.0.0/0"       # Dev: permite todo. Prod: ej. 192.168.1.0/24
    allowed_origin: str = "http://localhost:8501"  # Origen Streamlit para CORS

    # --- Streamlit ---
    streamlit_port: int = 8501
    api_base_url: str = "http://localhost:8000"


@lru_cache
def get_settings() -> Settings:
    """Devuelve la instancia cacheada de configuración (singleton)."""
    return Settings()
