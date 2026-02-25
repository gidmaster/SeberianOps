from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    app_env: str = "development"
    app_title: str = "SiberianOps"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    cache_ttl_dev: int = 10
    cache_ttl_prod: int = 3600
    admin_token: str = "changeme"
    site_url: str = "http://localhost:8000"
    trusted_hosts: list[str] = ["*"]
    site_description: str = "DevOps notes from Siberia"
    site_author: str = "GidMaster"
    database_url: str = "sqlite+aiosqlite:///./blog.db"

    @property
    def cache_ttl(self) -> int:
        return self.cache_ttl_dev if self.app_env == "development" else self.cache_ttl_prod

    @property
    def database_url_sync(self) -> str:
        replacements = {
            "sqlite+aiosqlite": "sqlite",
            "postgresql+asyncpg": "postgresql+psycopg2",
            "mysql+aiomysql": "mysql+pymysql",
        }
        url = self.database_url
        for async_driver, sync_driver in replacements.items():
            if url.startswith(async_driver):
                return url.replace(async_driver, sync_driver, 1)
        return url

    class Config:
        env_file = ".env"

settings = Settings()
