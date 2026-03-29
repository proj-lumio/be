"""OCR via Regolo AI — qwen3-vl-32b vision-language model."""

import base64

from app.services.llm import regolo_client

OCR_MODEL = "qwen3-vl-32b"


async def extract_text_from_image(file_bytes: bytes) -> str:
    """Extract text from an image using the vision-language model."""
    img_b64 = base64.b64encode(file_bytes).decode()

    # Detect mime type from magic bytes
    mime = "image/png"
    if file_bytes[:2] == b"\xff\xd8":
        mime = "image/jpeg"
    elif file_bytes[:4] == b"\x89PNG":
        mime = "image/png"
    elif file_bytes[:4] == b"RIFF":
        mime = "image/webp"

    response = await regolo_client.chat.completions.create(
        model=OCR_MODEL,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": (
                        "Extract all visible text from this image exactly as it appears. "
                        "Preserve the structure (headings, lists, tables). "
                        "Return only the extracted text, no commentary."
                    ),
                },
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime};base64,{img_b64}"},
                },
            ],
        }],
        max_tokens=4096,
        temperature=0.0,
    )
    return response.choices[0].message.content or ""
