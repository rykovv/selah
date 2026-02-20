from fastapi import FastAPI


def register_routes(app: FastAPI):
    """Include all route modules on the application."""
    from routes.dashboard import router as dashboard_router
    from routes.hymns import router as hymns_router
    from routes.programs import router as programs_router
    from routes.templates_mgr import router as templates_router
    from routes.api import router as api_router

    app.include_router(dashboard_router)
    app.include_router(hymns_router)
    app.include_router(programs_router)
    app.include_router(templates_router)
    app.include_router(api_router)
