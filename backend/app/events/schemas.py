from typing import Literal

from pydantic import BaseModel


class ThoughtCreated(BaseModel):
    event: Literal["thought.created"] = "thought.created"
    thought_id: str
    content: str


class FireNeuron(BaseModel):
    event: Literal["fire.neuron"] = "fire.neuron"
    thought_id: str
    agent_role: str
    task_summary: str


class GateItemCreated(BaseModel):
    event: Literal["gate.created"] = "gate.created"
    gate_item_id: str
    thought_id: str
    urgency: str


class GraphChanged(BaseModel):
    event: Literal["graph.changed"] = "graph.changed"
    change_type: Literal["node_created", "edge_created", "node_updated"]
    node_id: str | None = None
    edge_id: str | None = None
    extra: dict | None = None
