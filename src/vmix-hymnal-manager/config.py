import sys
import os


class Settings:
    APP_VERSION: str = "1.0.0a"
    DATABASE_URL: str = "sqlite:///./hymns.db"
    DEFAULT_DB_PATH: str = "hymns.db"
    UPLOAD_DIR: str = "templates"
    HOST: str = "0.0.0.0"
    PORT: int = 10001
    needs_setup: bool = False

    @staticmethod
    def resolve_template_dir() -> str:
        """Resolve Jinja2 template directory based on frozen/dev mode."""
        if getattr(sys, "frozen", False):
            base_dir = os.path.dirname(sys.executable)
            internal = os.path.join(base_dir, "_internal", "templates")
            root = os.path.join(base_dir, "templates")
            return internal if os.path.exists(internal) else root
        base_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(base_dir, "templates")


settings = Settings()
