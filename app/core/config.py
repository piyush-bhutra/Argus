from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    llm_api_key: str = ""
    llm_model: str = ""
    # OpenAI-SDK-compatible base URL for the LLM provider.
    #   Cerebras: https://api.cerebras.ai/v1
    #   Gemini:   https://generativelanguage.googleapis.com/v1beta/openai/
    llm_base_url: str = "https://api.cerebras.ai/v1"
    log_dir: str = "./logs"
    # Comma-separated browser origins allowed to call the API, or "*" for any.
    # Set this to the deployed frontend's origin in production.
    cors_origins: str = "*"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()

