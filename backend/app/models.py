from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


class Agent(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    model_provider: str = "anthropic"
    model_id: str = "claude-sonnet-5"
    hosting_mode: str = "api"  # "api" | "local" (local is a disabled stub)
    manifesto: Optional[str] = None
    system_prompt: Optional[str] = None
    model_api_key: Optional[str] = None
    capability_keys: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    capability_api_keys: dict[str, str] = Field(default_factory=dict, sa_column=Column(JSON))
    endpoints: list[dict] = Field(default_factory=list, sa_column=Column(JSON))
    cron_jobs: list[dict] = Field(default_factory=list, sa_column=Column(JSON))
    theme_color: str = "#aa3bff"
    status: str = "draft"  # "draft" | "deployed"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    deployed_at: Optional[datetime] = None
    container_id: Optional[str] = None
    container_port: Optional[int] = None

    @property
    def has_model_api_key(self) -> bool:
        return bool(self.model_api_key)

    @property
    def capability_api_keys_set(self) -> list[str]:
        return [key for key, value in self.capability_api_keys.items() if value]


class Message(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    agent_id: int = Field(foreign_key="agent.id", index=True)
    role: str  # "user" | "assistant"
    content: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
