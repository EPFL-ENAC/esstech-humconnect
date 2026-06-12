from functools import lru_cache

from pydantic_settings import BaseSettings


class Config(BaseSettings):
    OPENAI_API_URL: str
    OPENAI_API_KEY: str


@lru_cache()
def get_config():
    return Config()


config = get_config()
