from datetime import datetime, timezone
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ApiEnvelope(BaseModel, Generic[T]):
    version: str = "v1"
    ts: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    data: T
