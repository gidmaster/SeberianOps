from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    app_env: str = "development"
    app_title: str = "MyBlog"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    cache_ttl_dev: int = 10
    cache_ttl_prod: int = 3600
    admin_token: str = "changeme"

    @property
    def cache_ttl(self) -> int:
        return self.cache_ttl_dev if self.app_env == "development" else self.cache_ttl_prod

    class Config:
        env_file = ".env"

settings = Settings()