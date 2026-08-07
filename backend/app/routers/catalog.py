from fastapi import APIRouter

from app import docker_manager, mcp_manager
from app.registry import CAPABILITY_OPTIONS, MODEL_OPTIONS
from app.schemas import CapabilityOption, ModelOption

router = APIRouter(prefix="/api", tags=["catalog"])


@router.get("/models", response_model=list[ModelOption])
def list_models():
    return MODEL_OPTIONS


@router.get("/capabilities", response_model=list[CapabilityOption])
def list_capabilities():
    return [
        c.model_copy(update={"platform_key_available": bool(mcp_manager.platform_key_pool(c.key))})
        for c in CAPABILITY_OPTIONS
    ]


@router.get("/docker/status")
def docker_status():
    return {"available": docker_manager.is_available()}
