from functools import lru_cache

from pydantic_settings import BaseSettings


class Config(BaseSettings):
    OPENAI_API_URL: str
    OPENAI_API_KEY: str
    MEDITRON_MCP_API_KEY: str
    MEDITRON_MODEL_NAME: str = "OpenMeditron/Meditron3-70B"


@lru_cache()
def get_config():
    return Config()


config = get_config()
