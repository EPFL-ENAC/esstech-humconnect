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
    OPENAI_API_KEY_PREMIUM: str
    MEDITRON_MCP_API_KEY: str
    MODEL_NAME: str = "moonshotai/Kimi-K2.7-Code"
    MEDITRON_MODEL_NAME: str = "OpenMeditron/Meditron3-70B"
    LEGITRON_MODEL_NAME: str = "EPFLiGHT/Llama-33-70b-Legitron"

    KEYCLOAK_REALM: str = "EPFL"
    KEYCLOAK_URL: str = "https://enac-it-sso2.epfl.ch"
    KEYCLOAK_API_ID: str
    KEYCLOAK_API_SECRET: str
    KEYCLOAK_TOTP: bool = True

    MAX_WHYS: int = 5

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

    WHO_IRIS_API_BASE_URL: str = "https://iris.who.int/server/api"
    WHO_IRIS_TIMEOUT_SECONDS: float = 10
    WHO_IRIS_SEARCH_LIMIT: int = 5
    WHO_IRIS_MAX_DOCUMENTS: int = 3
    WHO_IRIS_EXCERPT_BYTES: int = 12_000

    SANIHUB_MCP_URL: str = "https://sanihub.washai.dev/api/test/mcp"
    SANIHUB_MCP_TIMEOUT_SECONDS: float = 30


@lru_cache()
def get_config():
    return Config()


config = get_config()
