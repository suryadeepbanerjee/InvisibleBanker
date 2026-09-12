from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # LLM
    groq_api_key: str = ""
    gemini_api_key: str = ""

    # Voice
    sarvam_api_key: str = ""
    sarvam_stt_model: str = "saaras:v4"

    # Knowledge ingestion
    firecrawl_api_key: str = ""

    # Supabase
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""

    # App config
    confidence_threshold: float = 0.75
    max_llm_retries: int = 3
    environment: str = "development"
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",")]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache()
def get_settings() -> Settings:
    return Settings()
