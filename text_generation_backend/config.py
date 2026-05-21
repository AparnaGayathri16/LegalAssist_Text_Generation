from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    HOST: str = "0.0.0.0"
    PORT: int = 8080
    AUTH_HOST: str = "0.0.0.0"
    AUTH_PORT: int = 8081
    timescale_service_url: str

    class Config:
        env_file = ".env"

settings = Settings()
