from functools import lru_cache

from pydantic_settings import BaseSettings


class Config(BaseSettings):
    APP_URL: str = "http://localhost:9000"
    API_PATH: str = ""

    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_NAME: str = "postgres"
    DB_USER: str
    DB_PASSWORD: str

    @property
    def DB_URL(self) -> str:
        return f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    OPENAI_API_URL: str
    OPENAI_API_KEY: str
    MEDITRON_MCP_API_KEY: str
    MODEL_NAME: str = "moonshotai/Kimi-K2.7-Code"

    KEYCLOAK_REALM: str = "EPFL"
    KEYCLOAK_URL: str = "https://enac-it-sso2.epfl.ch"
    KEYCLOAK_API_ID: str
    KEYCLOAK_API_SECRET: str
    KEYCLOAK_TOTP: bool = True

    NOMINATIM_BASE_URL: str = "https://nominatim.openstreetmap.org"
    NOMINATIM_TIMEOUT_SECONDS: float = 5

    NASA_EONET_BASE_URL: str = "https://eonet.gsfc.nasa.gov/api/v3"
    USGS_EARTHQUAKE_BASE_URL: str = "https://earthquake.usgs.gov/fdsnws/event/1"
    NATURAL_EVENTS_TIMEOUT_SECONDS: float = 5
    NATURAL_EVENTS_EARTHQUAKE_DAYS: int = 30
    NATURAL_EVENTS_PROVIDER_LIMIT: int = 20

    RELIEFWEB_BASE_URL: str = "https://api.reliefweb.int/v2"
    RELIEFWEB_APP_NAME: str = "EPFL-HumConnect-2026hwRSxljV0gLcE"
    HUMANITARIAN_CONTEXT_TIMEOUT_SECONDS: float = 5
    HUMANITARIAN_CONTEXT_DAYS: int = 30
    HUMANITARIAN_CONTEXT_LIMIT: int = 10

    SANIHUB_MCP_URL: str = "https://sanihub.washai.dev/api/test/mcp"
    SANIHUB_MCP_TIMEOUT_SECONDS: float = 30


@lru_cache()
def get_config():
    return Config()


config = get_config()
