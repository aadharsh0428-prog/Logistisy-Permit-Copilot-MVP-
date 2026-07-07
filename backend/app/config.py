from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://logistisy:logistisy@db:5432/logistisy"
    redis_url: str = "redis://redis:6379/0"

    # Local LLM via Ollama
    ollama_base_url: str = "http://ollama:11434"
    ollama_vision_model: str = "llama3.2-vision"
    ollama_text_model: str = "llama3.1"
    gemini_api_key: str = ""

    environment: str = "development"

    # Dev-mode flag: when true, re-uploading a file with a checksum that
    # already exists wipes the prior extraction and reprocesses it fresh,
    # instead of returning the cached Document. Useful while iterating on
    # prompts/parsing so the same test PDF can be re-run repeatedly without
    # manual SQL cleanup. Should be false in production.
    force_reprocess: bool = False

    class Config:
        env_file = ".env"


settings = Settings()