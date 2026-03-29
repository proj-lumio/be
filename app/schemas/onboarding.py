from pydantic import BaseModel, model_validator


class OnboardingAnalyzeRequest(BaseModel):
    description: str | None = None
    website_url: str | None = None

    @model_validator(mode="after")
    def at_least_one(self):
        if not self.description and not self.website_url:
            raise ValueError("Provide either 'description' or 'website_url'")
        if self.description and self.website_url:
            raise ValueError("Provide only one of 'description' or 'website_url', not both")
        return self


class CompanyProfile(BaseModel):
    name: str
    industry: str | None = None
    description: str | None = None
    services: list[str] = []
    products: list[str] = []
    target_market: str | None = None
    location: str | None = None
    website: str | None = None


class OnboardingAnalyzeResponse(BaseModel):
    profile: CompanyProfile
    source: str
    raw_extract: str | None = None


class OnboardingConfirmRequest(BaseModel):
    profile: CompanyProfile


class OnboardingConfirmResponse(BaseModel):
    company_id: str
    onboarding_completed: bool
    message: str


class OnboardingStatusResponse(BaseModel):
    onboarding_completed: bool
    company_id: str | None = None
