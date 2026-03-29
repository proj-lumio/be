"""Speech-to-text using Regolo's faster-whisper-large-v3 API."""

from app.config import get_settings

settings = get_settings()


async def transcribe_audio(file_path: str) -> str:
    """Transcribe audio/video file to text via Regolo API."""
    from openai import AsyncOpenAI

    client = AsyncOpenAI(
        api_key=settings.regolo_api_key,
        base_url=settings.regolo_base_url,
    )

    with open(file_path, "rb") as f:
        response = await client.audio.transcriptions.create(
            model="faster-whisper-large-v3",
            file=f,
        )

    return response.text
