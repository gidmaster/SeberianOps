from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    app_env: str = "development"
    app_title: str = "MyBlog"
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    class Config:
        env_file = ".env"

settings = Settings()
