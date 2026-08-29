from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    xai_api_key: str = ""
    log_dir: str = "./logs"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()
