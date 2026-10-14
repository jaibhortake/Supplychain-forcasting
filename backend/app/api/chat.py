from fastapi import APIRouter, HTTPException, status

from app.api.deps import ServiceDep
from app.schemas import ChatIn, ChatOut
from app.services import chat_service
from app.services.llm import LLMUnavailableError

router = APIRouter(tags=["assistant"])


@router.post("/chat", response_model=ChatOut)
def chat(body: ChatIn, svc: ServiceDep):
    """Ask a question about the forecast. Answers are grounded in the system's own numbers."""
    try:
        return chat_service.answer(body.message, [m.model_dump() for m in body.history], svc)
    except LLMUnavailableError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
