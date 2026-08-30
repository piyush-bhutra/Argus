from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    llm_api_key: str = ""
    llm_model: str = ""
    # OpenAI-SDK-compatible base URL for the LLM provider.
    #   Cerebras: https://api.cerebras.ai/v1
    #   Gemini:   https://generativelanguage.googleapis.com/v1beta/openai/
    llm_base_url: str = "https://api.cerebras.ai/v1"
    log_dir: str = "./logs"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()

