from urllib.parse import quote_plus

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "StayNest Pro"
    debug: bool = False

    db_user: str
    db_password: str
    db_host: str = "localhost"
    db_port: int = 3306
    db_name: str

    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""

    # day 3: optional. Without a key the AI features answer with simple rules
    anthropic_api_key: str = ""
    ai_model: str = "claude-haiku-5-5"

    model_config = SettingsConfigDict(env_file=".env")

    @property
    def database_url(self) -> str:
        # passwords like "abc@123" break the URL, so encode them first
        password = quote_plus(self.db_password)
        return f"mysql+pymysql://{self.db_user}:{password}@{self.db_host}:{self.db_port}/{self.db_name}"


settings = Settings()
