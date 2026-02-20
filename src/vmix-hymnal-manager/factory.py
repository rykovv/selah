import os

from fastapi import FastAPI
from fastapi.templating import Jinja2Templates

from config import settings
from database import Base, engine
from routes import register_routes


def create_app() -> FastAPI:
    """Application factory."""
    app = FastAPI()

    # Create database tables
    Base.metadata.create_all(bind=engine)

    # Ensure upload directory exists
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)

    # Setup Jinja2 templates on app state (accessible via request.app.state.templates)
    template_dir = settings.resolve_template_dir()
    app.state.templates = Jinja2Templates(directory=template_dir)

    # Register all route modules
    register_routes(app)

    return app
