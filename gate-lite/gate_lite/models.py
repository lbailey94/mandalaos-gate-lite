"""Gate-lite domain objects (v0 prototype)."""
import time
from dataclasses import dataclass, field
from enum import Enum


class SlotState(str, Enum):
    PLACED = "placed"
    ACTIVE = "active"
    FROZEN = "frozen"
    TERMINATED = "terminated"
    EXPIRED = "expired"
    DENIED = "denied"


SLOT_CLASSES = {
    "small": {"cpu_ms": 300000, "mem_mb": 1024, "disk_mb": 512},
    "medium": {"cpu_ms": 1200000, "mem_mb": 4096, "disk_mb": 2048},
}


def now_epoch() -> int:
    return int(time.time())


@dataclass
class Tenant:
    tenant_id: str
    agents: list[str] = field(default_factory=list)
    aup_version: str = "2026-09-17.1"
    settlement_ref: str | None = None


@dataclass
class Slot:
    slot_id: str
    tenant_id: str
    state: str
    slot_class: str
    quotas: dict
    created_at: int
    expires_at: int
    template: str = "default"
    pass_id: str | None = None


@dataclass
class Pass:
    pass_id: str
    slot_id: str
    agent_id: str
    principal_id: str | None
    expires_at: int
    quotas: dict
    spend_cap: dict | None
    jti: str
    token: str
