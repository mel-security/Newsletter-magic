from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Timezone
    tz: str = "Africa/Tunis"

    # Ollama
    ollama_base_url: str = "http://ollama:11434"
    model_writer: str = "mistral"
    model_critic: str = "deepseek-r1:7b"
    ollama_keep_alive: str = "0"

    # Scheduler
    daily_run_time: str = "06:30"

    # SMTP
    smtp_host: str = "mailhog"
    smtp_port: int = 1025
    smtp_user: str = ""
    smtp_pass: str = ""
    smtp_tls: bool = False
    from_email: str = "cyberagent@local.dev"
    to_emails: str = "admin@local.dev"

    # MailHog
    mailhog_enabled: bool = True

    # Pipeline
    max_articles_per_run: int = 200
    max_stories: int = 25
    lang: str = "fr"

    # Database
    database_url: str = "postgresql+asyncpg://cyberagent:changeme_in_production@postgres:5432/cyberagent"
    database_url_sync: str = "postgresql://cyberagent:changeme_in_production@postgres:5432/cyberagent"

    # Redis
    redis_url: str = "redis://redis:6379/0"

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Logging
    log_level: str = "info"
    log_format: str = "json"

    # Paths
    config_dir: str = "/opt/config"
    output_dir: str = "/opt/out"

    model_config = {"env_file": ".env", "extra": "ignore"}

    @property
    def to_emails_list(self) -> list[str]:
        return [e.strip() for e in self.to_emails.split(",") if e.strip()]


settings = Settings()
