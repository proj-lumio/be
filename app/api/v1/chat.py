import json
from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

from app.db.mongo import get_db
from app.middleware.auth import get_current_user
from app.services.chat_service import send_message_stream

router = APIRouter()


def _s(doc: dict) -> dict:
    """Serialize MongoDB doc for API response."""
    doc["id"] = str(doc.pop("_id"))
    for key in ("user_id", "company_id", "session_id"):
        if key in doc and isinstance(doc[key], ObjectId):
            doc[key] = str(doc[key])
    return doc


def _event_text(event: dict) -> str:
    return json.dumps(event, ensure_ascii=False)


@router.get("/sessions")
async def list_sessions(company_id: str | None = None, user: dict = Depends(get_current_user)):
    db = get_db()
    query = {"user_id": user["_id"]}
    if company_id:
        query["company_id"] = ObjectId(company_id)

    total = await db.chat_sessions.count_documents(query)
    cursor = db.chat_sessions.find(query).sort("updated_at", -1)
    items = [_s(doc) async for doc in cursor]
    return {"items": items, "total": total}


@router.post("/sessions", status_code=201)
async def create_session(data: dict, user: dict = Depends(get_current_user)):
    db = get_db()
    now = datetime.now(timezone.utc)
    session = {
        "user_id": user["_id"],
        "company_id": ObjectId(data["company_id"]),
        "title": data.get("title", "New Chat"),
        "created_at": now,
        "updated_at": now,
    }
    result = await db.chat_sessions.insert_one(session)
    session["_id"] = result.inserted_id
    return _s(session)


@router.get("/sessions/{session_id}")
async def get_session(session_id: str, user: dict = Depends(get_current_user)):
    db = get_db()
    session = await db.chat_sessions.find_one({"_id": ObjectId(session_id), "user_id": user["_id"]})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    cursor = db.chat_messages.find({"session_id": session["_id"]}).sort("created_at", 1)
    messages = [_s(m) async for m in cursor]

    resp = _s(session)
    resp["messages"] = messages
    return resp


@router.post("/sessions/{session_id}/messages")
async def send_chat_message(session_id: str, data: dict, user: dict = Depends(get_current_user)):
    db = get_db()
    session = await db.chat_sessions.find_one({"_id": ObjectId(session_id), "user_id": user["_id"]})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    async def event_generator():
        async for event in send_message_stream(session, user, data["content"]):
            yield f"data: {_event_text(event)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Credentials": "true",
        },
    )


@router.websocket("/sessions/{session_id}/ws")
async def chat_ws(websocket: WebSocket, session_id: str):
    """WebSocket streaming chat.

    Connect: ws(s)://<host>/api/v1/chat/sessions/{session_id}/ws?token=<jwt_token>
    (token is optional when DEV_AUTH_BYPASS=true)

    Client sends:   {"content": "user message"}
    Server streams:
      {"type": "chunk",    "data": "text delta"}
      {"type": "sources",  "data": {...}}
      {"type": "done",     "data": {"message_id": "..."}}
      {"type": "error",    "data": "error description"}
    """
    from app.config import get_settings
    settings = get_settings()
    db = get_db()

    # --- Auth via query param ---
    token = websocket.query_params.get("token")
    if settings.dev_auth_bypass:
        from app.middleware.auth import DEV_USER
        user = await db.users.find_one({"email": DEV_USER["email"]})
        if not user:
            await websocket.close(code=4001, reason="User not found")
            return
    else:
        if not token:
            await websocket.close(code=4001, reason="Missing token")
            return
        try:
            from app.middleware.auth import _verify_token
            payload = _verify_token(token)
            user = await db.users.find_one({"_id": ObjectId(payload["sub"])})
            if not user:
                await websocket.close(code=4001, reason="User not found")
                return
        except Exception:
            await websocket.close(code=4001, reason="Invalid token")
            return

    # --- Verify session ownership ---
    session = await db.chat_sessions.find_one({"_id": ObjectId(session_id), "user_id": user["_id"]})
    if not session:
        await websocket.close(code=4004, reason="Session not found")
        return

    await websocket.accept()

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_text(_event_text({"type": "error", "data": "Invalid JSON"}))
                continue

            content = data.get("content", "").strip()
            if not content:
                await websocket.send_text(_event_text({"type": "error", "data": "Empty message"}))
                continue

            try:
                async for event in send_message_stream(session, user, content):
                    await websocket.send_text(_event_text(event))
            except Exception as e:
                await websocket.send_text(_event_text({"type": "error", "data": str(e)}))
    except WebSocketDisconnect:
        pass


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(session_id: str, user: dict = Depends(get_current_user)):
    db = get_db()
    oid = ObjectId(session_id)
    result = await db.chat_sessions.delete_one({"_id": oid, "user_id": user["_id"]})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Session not found")
    await db.chat_messages.delete_many({"session_id": oid})
