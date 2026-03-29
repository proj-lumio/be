"""Regolo AI client — OpenAI-compatible API wrapper."""

from openai import AsyncOpenAI

from app.config import get_settings

settings = get_settings()

regolo_client = AsyncOpenAI(
    api_key=settings.regolo_api_key,
    base_url=settings.regolo_base_url,
)


async def chat_completion(
    messages: list[dict],
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 2048,
) -> dict:
    """Call Regolo AI chat completion endpoint.

    Returns dict with 'content', 'prompt_tokens', 'completion_tokens', 'total_tokens'.
    """
    response = await regolo_client.chat.completions.create(
        model=model or settings.regolo_model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    choice = response.choices[0]
    usage = response.usage
    return {
        "content": choice.message.content,
        "prompt_tokens": usage.prompt_tokens if usage else 0,
        "completion_tokens": usage.completion_tokens if usage else 0,
        "total_tokens": usage.total_tokens if usage else 0,
    }


async def chat_completion_stream(
    messages: list[dict],
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 2048,
):
    """Streaming chat completion. Yields (delta_text, usage_or_none) tuples.

    The last yielded item has delta="" and usage dict.
    """
    stream = await regolo_client.chat.completions.create(
        model=model or settings.regolo_model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        stream=True,
        stream_options={"include_usage": True},
    )
    async for chunk in stream:
        if chunk.choices:
            delta = chunk.choices[0].delta
            if delta and delta.content:
                yield delta.content, None
        if chunk.usage:
            yield "", {
                "prompt_tokens": chunk.usage.prompt_tokens,
                "completion_tokens": chunk.usage.completion_tokens,
                "total_tokens": chunk.usage.total_tokens,
            }


async def chat_completion_with_tools(
    messages: list[dict],
    tools: list[dict],
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> dict:
    """Chat completion with OpenAI-compatible function/tool calling.

    Returns dict with 'content', 'tool_calls', and token counts.
    tool_calls: list of {id, function: {name, arguments}} or empty list.
    """
    response = await regolo_client.chat.completions.create(
        model=model or settings.regolo_model,
        messages=messages,
        tools=tools,
        tool_choice="auto",
        temperature=temperature,
        max_tokens=max_tokens,
    )
    choice = response.choices[0]
    usage = response.usage

    tool_calls = []
    if choice.message.tool_calls:
        for tc in choice.message.tool_calls:
            tool_calls.append({
                "id": tc.id,
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            })

    return {
        "content": choice.message.content or "",
        "tool_calls": tool_calls,
        "prompt_tokens": usage.prompt_tokens if usage else 0,
        "completion_tokens": usage.completion_tokens if usage else 0,
        "total_tokens": usage.total_tokens if usage else 0,
    }


async def generate_session_title(user_message: str) -> str:
    """Generate a short chat session title from the first user message."""
    messages = [
        {"role": "system", "content": (
            "Generate a very short title (max 6 words) for a chat session based on the user's first message. "
            "The title should capture the topic/intent. Reply with ONLY the title, no quotes, no punctuation at the end. "
            "Use the same language as the user's message."
        )},
        {"role": "user", "content": user_message[:500]},
    ]
    result = await chat_completion(messages, temperature=0.3, max_tokens=30)
    title = (result["content"] or "").strip().strip('"\'').strip()
    return title[:60] if title else user_message[:50]


async def get_embeddings(texts: list[str], model: str = "Qwen3-Embedding-8B") -> list[list[float]]:
    """Get embeddings from Regolo AI (OpenAI-compatible)."""
    response = await regolo_client.embeddings.create(
        model=model,
        input=texts,
    )
    return [item.embedding for item in response.data]


async def extract_entities(text: str) -> dict:
    """Use LLM to extract entities and relationships from text for GraphRAG."""
    system_prompt = """You are an entity extraction system. Given a text, extract:
1. entities: list of {name, type, description}
2. relationships: list of {source, target, relation, description}

Types: PERSON, ORGANIZATION, LOCATION, PRODUCT, EVENT, CONCEPT, METRIC, DATE

Return JSON only, no markdown."""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": text[:4000]},  # Limit context
    ]
    result = await chat_completion(messages, temperature=0.0, max_tokens=4096)

    import json
    import re

    for attempt in range(3):
        if attempt > 0:
            result = await chat_completion(messages, temperature=0.0, max_tokens=4096)
        raw = (result["content"] or "").strip()
        # Strip markdown code fences if present
        m = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
        if m:
            raw = m.group(1).strip()
        # Strip <think>...</think> blocks (some models emit reasoning)
        raw = re.sub(r"<think>[\s\S]*?</think>", "", raw).strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            continue
    return {"entities": [], "relationships": []}


async def classify_company_categories(text: str) -> list[str]:
    """Classify a company into 1-3 macro-categories based on document content.

    Returns a list of valid category names from MACRO_CATEGORIE.
    """
    from app.constants.categories import MACRO_CATEGORIE, MACRO_CATEGORIE_STR

    system_prompt = f"""Sei un sistema di classificazione aziendale.
Data la descrizione o il contenuto documentale di un'azienda fornitrice, assegna da 1 a 3 macro-categorie dalla seguente lista:
{MACRO_CATEGORIE_STR}

Regole:
- Scegli SOLO categorie dalla lista sopra, non inventarne di nuove.
- Assegna minimo 1 e massimo 3 categorie.
- Basati sul contenuto del documento per capire il settore dell'azienda.

Rispondi SOLO con JSON valido, senza markdown:
{{"categorie": ["Categoria1", "Categoria2"]}}"""

    import json
    import re

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": text[:6000]},
    ]

    for attempt in range(3):
        if attempt > 0:
            result = await chat_completion(messages, temperature=0.0, max_tokens=256)
        else:
            result = await chat_completion(messages, temperature=0.0, max_tokens=256)
        raw = (result["content"] or "").strip()
        m = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
        if m:
            raw = m.group(1).strip()
        raw = re.sub(r"<think>[\s\S]*?</think>", "", raw).strip()
        try:
            data = json.loads(raw)
            categories = [c for c in data.get("categorie", []) if c in MACRO_CATEGORIE]
            if categories:
                return categories[:3]
        except json.JSONDecodeError:
            continue
    return []


async def extract_contract_data(text: str) -> dict | None:
    """Extract structured financial/contractual data from a contract document.

    Returns None if the text is not a contract.
    """
    system_prompt = """You are a contract analysis system. Given a document text, determine if it is a contract.
If it is NOT a contract, return: {"is_contract": false}

If it IS a contract, extract structured data and return JSON with this exact schema:
{
  "is_contract": true,
  "vendor_name": "string — the company providing the service",
  "client_name": "string — the company receiving the service",
  "contract_type": "string — e.g. SaaS License, Consulting, Maintenance",
  "signature_date": "YYYY-MM-DD or null",
  "financials": {
    "canone_trimestrale_eur": number or null,
    "canone_annualizzato_eur": number or null,
    "pricing_model": "string — e.g. flat, per_page_tiered, per_user",
    "variable_fees": [{"range": "string", "unit_price_cents": number}]
  },
  "sla": {
    "uptime_target_pct": number or null,
    "uptime_minimum_pct": number or null,
    "credit_uptime_pct": number or null,
    "credit_ticketing_pct": number or null,
    "credit_cap_pct": number or null
  },
  "terms": {
    "duration_months": number or null,
    "notice_days": number or null,
    "auto_renewal": boolean or null,
    "liability_cap_pct": number or null,
    "data_retention_days": number or null
  },
  "risk_flags": ["string — e.g. short_data_retention, low_liability_cap, long_notice_period, no_data_portability"],
  "criticality_auto": number 1-5 (1=low, 5=critical) based on service importance, financial exposure, and replaceability
}

Return JSON only, no markdown. Use null for fields you cannot determine."""

    import json
    import re

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": text[:8000]},
    ]

    for attempt in range(3):
        result = await chat_completion(messages, temperature=0.0, max_tokens=4096)
        raw = (result["content"] or "").strip()
        m = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
        if m:
            raw = m.group(1).strip()
        raw = re.sub(r"<think>[\s\S]*?</think>", "", raw).strip()
        try:
            data = json.loads(raw)
            if not data.get("is_contract", False):
                return None
            data.pop("is_contract", None)
            return data
        except json.JSONDecodeError:
            continue
    return None
