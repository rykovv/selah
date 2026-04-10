"""vMix Church Service Manager -- application entry point."""

import uvicorn

from config import settings
from factory import create_app

app = create_app()

if __name__ == "__main__":
    uvicorn.run(app, host=settings.HOST, port=settings.PORT)
