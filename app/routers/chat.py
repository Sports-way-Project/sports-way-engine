from fastapi import APIRouter

from app.models.chat_schemas import ChatRequest, ChatResponse
from app.services import chat_service

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/website", response_model=ChatResponse)
async def chat_website(payload: ChatRequest):
    """Public storefront chatbot — restricted scope, can hand off to WhatsApp."""
    reply = await chat_service.get_website_reply(payload.message)
    return ChatResponse(reply=reply)


@router.post("/internal", response_model=ChatResponse)
async def chat_internal(payload: ChatRequest):
    """Internal Dolibarr sales copilot — fuller access, staff-only."""
    reply = await chat_service.get_internal_reply(payload.message)
    return ChatResponse(reply=reply)
