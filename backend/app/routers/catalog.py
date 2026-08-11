from fastapi import APIRouter
from pydantic import BaseModel

from app import docker_manager, llm_client, mcp_manager
from app.registry import CAPABILITY_OPTIONS, MODEL_OPTIONS
from app.schemas import CapabilityOption, ModelOption

router = APIRouter(prefix="/api", tags=["catalog"])


@router.get("/models", response_model=list[ModelOption])
def list_models():
    return MODEL_OPTIONS


class RecommendRequest(BaseModel):
    purpose: str


@router.post("/models/recommend")
def recommend_model(payload: RecommendRequest):
    """Suggest a model for an agent's stated purpose.

    Deliberately never fails: the wizard shows a suggestion when there is one
    and simply doesn't when there isn't, so a Groq hiccup can't block someone
    from picking a model themselves."""
    purpose = payload.purpose.strip()
    if not purpose:
        return {"recommendation": None}
    return {"recommendation": llm_client.recommend_model(purpose, MODEL_OPTIONS)}


@router.get("/capabilities", response_model=list[CapabilityOption])
def list_capabilities():
    return [
        c.model_copy(update={"platform_key_available": bool(mcp_manager.platform_key_pool(c.key))})
        for c in CAPABILITY_OPTIONS
    ]


@router.get("/docker/status")
def docker_status():
    return {"available": docker_manager.is_available()}
