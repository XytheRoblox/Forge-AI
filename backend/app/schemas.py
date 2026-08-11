from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class EndpointSpec(BaseModel):
    id: str
    path: str
    method: str = "POST"
    description: str = ""
    input_schema: dict
    instruction: str


class CronJobSpec(BaseModel):
    id: str
    cron_expression: str
    instruction: str


class AgentCreate(BaseModel):
    name: str
    # Kept in sync by hand with registry.MODEL_OPTIONS — registry imports this
    # module, so it can't be imported back here to derive the default.
    model_provider: str = "featherless"
    model_id: str = "Qwen/Qwen2.5-72B-Instruct"
    hosting_mode: str = "api"
    manifesto: Optional[str] = None
    system_prompt: Optional[str] = None
    model_api_key: Optional[str] = None
    capability_keys: list[str] = []
    capability_api_keys: dict[str, str] = {}
    endpoints: list[EndpointSpec] = []
    cron_jobs: list[CronJobSpec] = []
    theme_color: str = "#aa3bff"


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    model_provider: Optional[str] = None
    model_id: Optional[str] = None
    hosting_mode: Optional[str] = None
    manifesto: Optional[str] = None
    system_prompt: Optional[str] = None
    model_api_key: Optional[str] = None
    capability_keys: Optional[list[str]] = None
    capability_api_keys: Optional[dict[str, str]] = None
    endpoints: Optional[list[EndpointSpec]] = None
    cron_jobs: Optional[list[CronJobSpec]] = None
    theme_color: Optional[str] = None


class AgentRead(BaseModel):
    id: int
    name: str
    model_provider: str
    model_id: str
    hosting_mode: str
    manifesto: Optional[str]
    system_prompt: Optional[str]
    has_model_api_key: bool
    capability_keys: list[str]
    capability_api_keys_set: list[str]
    endpoints: list[EndpointSpec]
    cron_jobs: list[CronJobSpec]
    theme_color: str
    status: str
    created_at: datetime
    deployed_at: Optional[datetime]
    container_id: Optional[str]
    container_port: Optional[int]
    service_url: Optional[str]
    cloudrun_service_name: Optional[str]
    connected_accounts: dict[str, str] = {}

    model_config = ConfigDict(from_attributes=True)


class ThemeUpdate(BaseModel):
    theme_color: str


class ExpandManifestoRequest(BaseModel):
    manifesto: str


class ExpandManifestoResponse(BaseModel):
    system_prompt: str


class ChatImage(BaseModel):
    data: str  # base64, no data: URI prefix
    media_type: str


class ChatRequest(BaseModel):
    message: str
    image: Optional[ChatImage] = None


class MessageRead(BaseModel):
    id: int
    role: str
    content: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ChatResponse(BaseModel):
    reply: MessageRead
    history: list[MessageRead]


class ModelOption(BaseModel):
    provider: str  # who serves it — drives which client the runtime uses
    provider_label: str
    family: str  # who built the weights — drives how the picker groups them
    family_label: str
    model_id: str
    label: str
    description: str
    available: bool


class CapabilityOption(BaseModel):
    key: str
    name: str
    description: str
    icon: str
    wired: bool
    mcp_server: Optional[str] = None
    requires_api_key: bool = False
    api_key_help: Optional[str] = None
    platform_key_available: bool = False
    # Set when the capability reaches a third party's account rather than a
    # keyed API — the wizard asks the user to authorise instead of asking for
    # a key. One grant covers every capability sharing the provider.
    oauth_provider: Optional[str] = None
    oauth_scopes: list[str] = []


class BuildStepStatus(BaseModel):
    name: str
    status: str  # "pending" | "running" | "success" | "failed"
    detail: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class BuildJobRead(BaseModel):
    id: str
    agent_id: int
    status: str  # "running" | "success" | "failed"
    steps: list[BuildStepStatus]

    model_config = ConfigDict(from_attributes=True)


class BuildStartResponse(BaseModel):
    job_id: str
