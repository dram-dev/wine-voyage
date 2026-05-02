import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    database_url: str
    anthropic_api_key: str
    port: int


def load_settings() -> Settings:
    database_url = os.getenv("DATABASE_URL", "postgresql://localhost/winevoyage")
    anthropic_api_key = os.getenv("ANTHROPIC_API_KEY", "")
    port = int(os.getenv("PORT", "8420"))
    return Settings(
        database_url=database_url,
        anthropic_api_key=anthropic_api_key,
        port=port,
    )


settings = load_settings()
