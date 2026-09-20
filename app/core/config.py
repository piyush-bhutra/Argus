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

    # POST /debate/start is unauthenticated and each call spends ~6 LLM
    # requests, so without a cap the endpoint is an open proxy onto the
    # operator's quota. Defaults are deliberately tight; raise them knowingly.
    debate_rate_limit: int = 5
    debate_rate_window_seconds: float = 300.0
    # Honour X-Forwarded-For for client identity. The header is client-supplied
    # and trivially spoofed, so enable this ONLY when the app genuinely sits
    # behind a proxy that overwrites it — otherwise it defeats the rate limit.
    trust_proxy_headers: bool = False

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()

