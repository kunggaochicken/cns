from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, model_validator

ToolName = Literal[
    "vault_read",
    "vault_write",
    "run_tests",
    "stage_commits",
    "linear_read",
    "github_read",
]


class AgentSpec(BaseModel):
    id: str
    role: str
    persona: str
    enabled: bool = True
    tools: list[ToolName] = []
    escalates_to: str | None = None


class FleetConfig(BaseModel):
    agents: list[AgentSpec] = []

    @model_validator(mode="after")
    def _check_unique_ids(self):
        seen: set[str] = set()
        for a in self.agents:
            if a.id in seen:
                raise ValueError(f"duplicate agent id: {a.id}")
            seen.add(a.id)
        return self


def load_fleet_config(path: Path | str) -> FleetConfig:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Fleet config not found: {path}")
    with path.open() as f:
        data = yaml.safe_load(f) or {}
    return FleetConfig.model_validate(data)
