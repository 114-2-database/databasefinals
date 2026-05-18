from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="")

    database_url: str = "mysql+pymysql://user:password@localhost:3306/nccu_grad"
    session_secret: str = "dev-secret"


settings = Settings()

DATABASE_URL = settings.database_url
SESSION_SECRET = settings.session_secret
