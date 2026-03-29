from pydantic import BaseModel


# ── OpenAPI IT nested models ───────────────────────────────────────────

class BalanceSheet(BaseModel):
    year: int | None = None
    employees: int | None = None
    balanceSheetDate: str | None = None
    turnover: float | None = None
    netWorth: float | None = None
    shareCapital: float | None = None
    totalStaffCost: float | None = None
    totalAssets: float | None = None
    avgGrossSalary: float | None = None


class Shareholder(BaseModel):
    companyName: str | None = None
    name: str | None = None
    surname: str | None = None
    taxCode: str | None = None
    percentShare: float | None = None


class GruppoIva(BaseModel):
    vatGroupParticipation: bool = False
    isVatGroupLeader: bool = False
    registryOk: bool = True


# ── Company schemas ────────────────────────────────────────────────────

class CompanyCreate(BaseModel):
    name: str
    description: str | None = None
    industry: str | None = None
    website: str | None = None
    logo_url: str | None = None
    # OpenAPI IT fields (optional, populated via /enrich)
    piva: str | None = None
    ragione_sociale: str | None = None
    forma_giuridica: str | None = None
    data_costituzione: str | None = None
    indirizzo: str | None = None
    cap: str | None = None
    citta: str | None = None
    provincia: str | None = None
    regione: str | None = None
    ateco: str | None = None
    ateco_description: str | None = None
    ateco_2022: str | None = None
    ateco_2007: str | None = None
    dipendenti: int | None = None
    fatturato: float | None = None
    capitale_sociale: float | None = None
    pec: str | None = None
    sdi: str | None = None
    stato_attivita: str | None = None
    rea_code: str | None = None
    cciaa: str | None = None
    codice_catastale: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    data_inizio_attivita: str | None = None
    data_chiusura: str | None = None
    cessata: bool | None = None
    gruppo_iva: GruppoIva | None = None
    bilanci: list[BalanceSheet] | None = None
    azionisti: list[Shareholder] | None = None
    # Web enrichment fields
    email_aziendale: str | None = None
    telefono_aziendale: str | None = None
    linkedin_url: str | None = None
    facebook_url: str | None = None
    instagram_url: str | None = None
    twitter_url: str | None = None
    descrizione: str | None = None
    marchi_registrati: list[dict] | None = None
    news_recenti: list[dict] | None = None
    punti_chiave: list[str] | None = None
    settore_label: str | None = None


class CompanyUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    industry: str | None = None
    website: str | None = None
    logo_url: str | None = None
    piva: str | None = None
    ragione_sociale: str | None = None
    forma_giuridica: str | None = None
    data_costituzione: str | None = None
    indirizzo: str | None = None
    cap: str | None = None
    citta: str | None = None
    provincia: str | None = None
    regione: str | None = None
    ateco: str | None = None
    ateco_description: str | None = None
    ateco_2022: str | None = None
    ateco_2007: str | None = None
    dipendenti: int | None = None
    fatturato: float | None = None
    capitale_sociale: float | None = None
    pec: str | None = None
    sdi: str | None = None
    stato_attivita: str | None = None
    rea_code: str | None = None
    cciaa: str | None = None
    codice_catastale: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    data_inizio_attivita: str | None = None
    data_chiusura: str | None = None
    cessata: bool | None = None
    gruppo_iva: GruppoIva | None = None
    bilanci: list[BalanceSheet] | None = None
    azionisti: list[Shareholder] | None = None
    email_aziendale: str | None = None
    telefono_aziendale: str | None = None
    linkedin_url: str | None = None
    facebook_url: str | None = None
    instagram_url: str | None = None
    twitter_url: str | None = None
    descrizione: str | None = None
    marchi_registrati: list[dict] | None = None
    news_recenti: list[dict] | None = None
    punti_chiave: list[str] | None = None
    settore_label: str | None = None


class CompanyResponse(BaseModel):
    id: str
    owner_id: str
    name: str
    description: str | None = None
    industry: str | None = None
    website: str | None = None
    logo_url: str | None = None
    categories: list[str] | None = None
    source: str | None = None
    ranking_score: float = 0.0
    client_score: float = 0.0
    total_annual_revenue_eur: float = 0.0
    created_at: str | None = None
    updated_at: str | None = None
    # OpenAPI IT fields
    piva: str | None = None
    ragione_sociale: str | None = None
    forma_giuridica: str | None = None
    data_costituzione: str | None = None
    indirizzo: str | None = None
    cap: str | None = None
    citta: str | None = None
    provincia: str | None = None
    regione: str | None = None
    ateco: str | None = None
    ateco_description: str | None = None
    ateco_2022: str | None = None
    ateco_2007: str | None = None
    dipendenti: int | None = None
    fatturato: float | None = None
    capitale_sociale: float | None = None
    pec: str | None = None
    sdi: str | None = None
    stato_attivita: str | None = None
    rea_code: str | None = None
    cciaa: str | None = None
    codice_catastale: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    data_inizio_attivita: str | None = None
    data_chiusura: str | None = None
    cessata: bool | None = None
    gruppo_iva: GruppoIva | None = None
    bilanci: list[BalanceSheet] | None = None
    azionisti: list[Shareholder] | None = None
    openapi_enriched_at: str | None = None
    # Web enrichment fields
    email_aziendale: str | None = None
    telefono_aziendale: str | None = None
    linkedin_url: str | None = None
    facebook_url: str | None = None
    instagram_url: str | None = None
    twitter_url: str | None = None
    descrizione: str | None = None
    marchi_registrati: list[dict] | None = None
    news_recenti: list[dict] | None = None
    punti_chiave: list[str] | None = None
    settore_label: str | None = None
    confidence_scores: dict | None = None
    enriched_categories: list[str] | None = None
    enriched_at: str | None = None

    model_config = {"from_attributes": True}


class CompanyListResponse(BaseModel):
    items: list[CompanyResponse]
    total: int
    page: int
    page_size: int
