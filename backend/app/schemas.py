from datetime import datetime
from typing import Optional

from pydantic import BaseModel


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
    model_provider: str = "anthropic"
    model_id: str = "claude-sonnet-5"
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

    class Config:
        from_attributes = True


class ThemeUpdate(BaseModel):
    theme_color: str


class ExpandManifestoRequest(BaseModel):
    manifesto: str


class ExpandManifestoResponse(BaseModel):
    system_prompt: str


class ChatRequest(BaseModel):
    message: str


class MessageRead(BaseModel):
    id: int
    role: str
    content: str
    created_at: datetime

    class Config:
        from_attributes = True


class ChatResponse(BaseModel):
    reply: MessageRead
    history: list[MessageRead]


class ModelOption(BaseModel):
    provider: str
    provider_label: str
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


class BuildStepStatus(BaseModel):
    name: str
    status: str  # "pending" | "running" | "success" | "failed"
    detail: Optional[str] = None

    class Config:
        from_attributes = True


class BuildJobRead(BaseModel):
    id: str
    agent_id: int
    status: str  # "running" | "success" | "failed"
    steps: list[BuildStepStatus]

    class Config:
        from_attributes = True


class BuildStartResponse(BaseModel):
    job_id: str
