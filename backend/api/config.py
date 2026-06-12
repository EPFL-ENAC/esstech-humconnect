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
    MODEL_NAME: str = "moonshotai/Kimi-K2.6"


@lru_cache()
def get_config():
    return Config()


config = get_config()
