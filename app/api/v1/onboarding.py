"""Onboarding endpoints — analyze company from URL/description, confirm profile."""

from fastapi import APIRouter, Depends, HTTPException

from app.middleware.auth import get_current_user
from app.schemas.onboarding import (
    OnboardingAnalyzeRequest,
    OnboardingAnalyzeResponse,
    OnboardingConfirmRequest,
    OnboardingConfirmResponse,
    OnboardingStatusResponse,
)
from app.services.onboarding_service import (
    analyze_from_website,
    analyze_from_description,
    confirm_onboarding,
    get_onboarding_status,
)

router = APIRouter()


@router.post("/analyze", response_model=OnboardingAnalyzeResponse)
async def analyze(data: OnboardingAnalyzeRequest, user: dict = Depends(get_current_user)):
    """Analyze company from URL or free-text description. Returns structured profile for review."""
    try:
        if data.website_url:
            profile, raw = await analyze_from_website(data.website_url)
            return OnboardingAnalyzeResponse(profile=profile, source="website", raw_extract=raw)
        else:
            profile = await analyze_from_description(data.description)
            return OnboardingAnalyzeResponse(profile=profile, source="description")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/confirm", response_model=OnboardingConfirmResponse)
async def confirm(data: OnboardingConfirmRequest, user: dict = Depends(get_current_user)):
    """Confirm onboarding profile. Creates/updates company and marks onboarding done."""
    result = await confirm_onboarding(user, data.profile)
    return OnboardingConfirmResponse(
        company_id=result["company_id"],
        onboarding_completed=result["onboarding_completed"],
        message="Onboarding completed. Company profile saved.",
    )


@router.get("/status", response_model=OnboardingStatusResponse)
async def status(user: dict = Depends(get_current_user)):
    """Check whether the current user has completed onboarding."""
    return await get_onboarding_status(user)
