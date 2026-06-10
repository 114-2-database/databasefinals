from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="")
    database_url: str = "mysql+pymysql://user:password@localhost:3306/nccu_grad"
    session_secret: str = "dev-secret"
    jwt_expiration_minutes: int = 30
    secret_key: str
    jwt_algorithm: str = "HS256"



settings = Settings()

DATABASE_URL = settings.database_url
SESSION_SECRET = settings.session_secret
JWT_EXPIRATION_MINUTES = settings.jwt_expiration_minutes
SECRET_KEY = settings.secret_key
JWT_ALGORITHM = settings.jwt_algorithm
