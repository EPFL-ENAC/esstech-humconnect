from openai import AsyncOpenAI

from api.config import config

openai_client = AsyncOpenAI(
    base_url=config.OPENAI_API_URL,
    api_key=config.OPENAI_API_KEY,
)

# model=config.MODEL_NAME
