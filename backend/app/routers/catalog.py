import jsonschema
from fastapi import APIRouter
from pydantic import BaseModel

from app import docker_manager, llm_client, mcp_manager
from app.build_pipeline import _sample_payload
from app.registry import CAPABILITY_OPTIONS, ENDPOINT_TEMPLATES, MODEL_OPTIONS
from app.schemas import CapabilityOption, EndpointTemplate, ModelOption

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


@router.get("/endpoint-templates", response_model=list[EndpointTemplate])
def list_endpoint_templates():
    """Ready-made endpoints, with the suggested capability's display name
    resolved so the picker doesn't need the capability catalog too."""
    names = {c.key: c.name for c in CAPABILITY_OPTIONS}
    return [
        t.model_copy(update={"suggested_capability_name": names.get(t.suggested_capability or "")})
        for t in ENDPOINT_TEMPLATES
    ]


class SuggestEndpointsRequest(BaseModel):
    name: str = ""
    purpose: str = ""
    capability_keys: list[str] = []
    taken_paths: list[str] = []


@router.post("/endpoint-templates/recommend")
def suggest_endpoints(payload: SuggestEndpointsRequest):
    """Propose endpoints that fit this particular agent.

    Never fails: the wizard shows suggestions when there are some and the
    stock templates alone when there aren't, so a Groq hiccup can't stand
    between someone and an endpoint they could have added by hand.

    Each suggestion is put through the same probe the deploy smoke test uses,
    because a suggestion that fails to deploy is worse than no suggestion —
    the failure would surface minutes later, on a build, attributed to
    something the user chose rather than something we generated."""
    names = {c.key: c.name for c in CAPABILITY_OPTIONS}
    suggestions = llm_client.suggest_endpoints(
        name=payload.name,
        purpose=payload.purpose,
        capability_names=[names[k] for k in payload.capability_keys if k in names],
        taken_paths=[t.path for t in ENDPOINT_TEMPLATES] + payload.taken_paths,
    )

    deployable = []
    for s in suggestions:
        try:
            jsonschema.validate(_sample_payload(s["input_schema"]), s["input_schema"])
        except jsonschema.ValidationError:
            continue
        deployable.append(s)
    return {"recommendations": deployable}


@router.get("/docker/status")
def docker_status():
    return {"available": docker_manager.is_available()}
