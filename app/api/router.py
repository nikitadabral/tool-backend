from fastapi import APIRouter

from app.api.routes import auth, intake

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(intake.router)
