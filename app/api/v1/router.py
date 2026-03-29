from fastapi import APIRouter

from app.api.v1 import (
    health, auth, companies, documents, chat, rankings,
    analytics, settings, landing, contracts, onboarding,
    web_search, general_chat, backoffice,
)

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["Auth"])
api_router.include_router(health.router, prefix="/health", tags=["Health"])
api_router.include_router(companies.router, prefix="/companies", tags=["Companies"])
api_router.include_router(documents.router, prefix="/companies/{company_id}/documents", tags=["Documents"])
api_router.include_router(contracts.router, prefix="/companies/{company_id}/contracts", tags=["Contracts"])
api_router.include_router(chat.router, prefix="/chat", tags=["Chat"])
api_router.include_router(general_chat.router, prefix="/general-chat", tags=["General Chat"])
api_router.include_router(web_search.router, prefix="/web-search", tags=["Web Search"])
api_router.include_router(rankings.router, prefix="/rankings", tags=["Rankings"])
api_router.include_router(analytics.router, prefix="/analytics", tags=["Analytics"])
api_router.include_router(settings.router, prefix="/settings", tags=["Settings"])
api_router.include_router(landing.router, prefix="/landing", tags=["Landing"])
api_router.include_router(onboarding.router, prefix="/onboarding", tags=["Onboarding"])
api_router.include_router(backoffice.router, prefix="/backoffice", tags=["Backoffice"])
