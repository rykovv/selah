import sys
import os

from paths import data_dir, is_frozen, migrate_legacy_layout


class Settings:
    APP_VERSION: str = "1.4.0"
    GITHUB_REPO: str = "rykovv/vmix-church-service-manager"
    HOST: str = "0.0.0.0"
    PORT: int = 10001
    needs_setup: bool = False

    def __init__(self):
        if is_frozen():
            # Installed app: dynamic data lives in %APPDATA%, never next to
            # the executable (which the installer may wipe on update).
            migrate_legacy_layout()
            base = data_dir()
            self.DEFAULT_DB_PATH = os.path.join(base, "hymns.db")
            self.UPLOAD_DIR = os.path.join(base, "templates")
        else:
            # Development: keep the historical source-dir-relative layout
            self.DEFAULT_DB_PATH = "hymns.db"
            self.UPLOAD_DIR = "templates"
        self.DATABASE_URL = f"sqlite:///{self.DEFAULT_DB_PATH}"

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
