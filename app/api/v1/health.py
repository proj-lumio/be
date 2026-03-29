import asyncio
import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

router = APIRouter()


@router.get("")
async def health_check():
    return {"status": "ok", "service": "lumio-api", "version": "0.1.0"}


@router.get("/sse-test")
async def sse_test():
    """Minimal SSE test — streams 5 chunks with 0.3s delay each."""
    async def generate():
        for i in range(5):
            yield f"data: {json.dumps({'type': 'chunk', 'data': f'Token {i} '})}\n\n"
            await asyncio.sleep(0.3)
        yield f"data: {json.dumps({'type': 'done', 'data': {'message_id': 'test'}})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
        },
    )
