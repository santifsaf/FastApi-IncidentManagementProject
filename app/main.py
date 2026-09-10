"""Punto de entrada de FastAPI.

La estructura de la base de datos se administra exclusivamente con Alembic;
la aplicacion no crea ni modifica tablas durante el arranque.
"""

from fastapi import FastAPI

from app.api.routes.auth import router as auth_router
from app.api.routes.categories import router as categories_router
from app.api.routes.teams import router as teams_router
from app.api.routes.tickets import router as tickets_router
from app.api.routes.users import router as users_router
from app.core.config import settings


app = FastAPI(
    title=settings.app_name,
)

app.include_router(auth_router)
app.include_router(categories_router)
app.include_router(teams_router)
app.include_router(tickets_router)
app.include_router(users_router)
