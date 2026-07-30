from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes.auth import router as auth_router
from app.api.routes.categories import router as categories_router
from app.api.routes.teams import router as teams_router
from app.api.routes.tickets import router as tickets_router
from app.api.routes.users import router as users_router
from app.core.config import settings
#from app.db.base import Base
#from app.db.session import engine                  ESTO ESTA COMENTADO PORQUE ESTAMOS USANDO ALEMBIC 
#from app.models.ticket import Ticket
#from app.models.user import User


# @asynccontextmanager
# async def lifespan(app: FastAPI):
    # Asegura que SQLAlchemy conozca los modelos importados y cree las tablas
    # faltantes cuando la aplicación arranca.
    #Base.metadata.create_all(bind=engine) ESTO ESTA COMENTADO PORQUE ESTAMOS USANDO ALEMBIC 
#     yield


app = FastAPI(
     title=settings.app_name,
    #  lifespan=lifespan,
)

app.include_router(auth_router)
app.include_router(categories_router)
app.include_router(teams_router)
app.include_router(tickets_router)
app.include_router(users_router)
