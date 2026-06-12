from functools import lru_cache

from pydantic_settings import BaseSettings


class Config(BaseSettings):
    APP_URL: str = "http://localhost:9000"
    API_PATH: str = ""

    OPENAI_API_URL: str
    OPENAI_API_KEY: str
    MODEL_NAME: str = "moonshotai/Kimi-K2.6"


@lru_cache()
def get_config():
    return Config()


config = get_config()
