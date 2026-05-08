from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import BaseModel, Field
from pydantic import (
    Field as PydField,
)  # alias used for discriminated-union Annotated metadata


def _gen_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:10]}"


def _now() -> datetime:
    return datetime.now(UTC)


class NodeType(StrEnum):
    THOUGHT = "thought"
    BET = "bet"
    TASK = "task"
    DECISION = "decision"
    CONFLICT = "conflict"
    OUTCOME = "outcome"
    AGENT_FIRING = "agent_firing"
    CODE_CHANGE = "code_change"
    CONVERSATION = "conversation"
    DOC = "doc"
    GATE_ITEM = "gate_item"
    AGENT = "agent"


class _BaseNode(BaseModel):
    id: str
    created_at: datetime = Field(default_factory=_now)
    embedding_id: str | None = None


class ThoughtNode(_BaseNode):
    node_type: Literal[NodeType.THOUGHT] = NodeType.THOUGHT
    id: str = Field(default_factory=lambda: _gen_id("t"))
    content: str
    source: str  # pwa | voice | web | cli | obsidian | linear | github
    metadata: dict = Field(default_factory=dict)


class BetNode(_BaseNode):
    node_type: Literal[NodeType.BET] = NodeType.BET
    id: str = Field(default_factory=lambda: _gen_id("b"))
    slug: str
    title: str
    vault_path: str
    owner: str
    horizon: str = "Q"
    confidence: str = "medium"


class TaskNode(_BaseNode):
    node_type: Literal[NodeType.TASK] = NodeType.TASK
    id: str = Field(default_factory=lambda: _gen_id("k"))
    linear_id: str
    title: str
    status: str = "todo"


class DecisionNode(_BaseNode):
    node_type: Literal[NodeType.DECISION] = NodeType.DECISION
    id: str = Field(default_factory=lambda: _gen_id("d"))
    content: str
    decided_by: str
    reasoning: str = ""


class ConflictNode(_BaseNode):
    node_type: Literal[NodeType.CONFLICT] = NodeType.CONFLICT
    id: str = Field(default_factory=lambda: _gen_id("c"))
    summary: str
    severity: str = "medium"


class OutcomeNode(_BaseNode):
    node_type: Literal[NodeType.OUTCOME] = NodeType.OUTCOME
    id: str = Field(default_factory=lambda: _gen_id("o"))
    summary: str
    success: bool


class AgentFiringNode(_BaseNode):
    node_type: Literal[NodeType.AGENT_FIRING] = NodeType.AGENT_FIRING
    id: str = Field(default_factory=lambda: _gen_id("f"))
    agent_id: str
    trace_id: str
    started_at: datetime = Field(default_factory=_now)
    completed_at: datetime | None = None
    outcome: str | None = None  # success | partial | failed


class CodeChangeNode(_BaseNode):
    node_type: Literal[NodeType.CODE_CHANGE] = NodeType.CODE_CHANGE
    id: str = Field(default_factory=lambda: _gen_id("cc"))
    repo: str
    sha: str
    summary: str


class ConversationNode(_BaseNode):
    node_type: Literal[NodeType.CONVERSATION] = NodeType.CONVERSATION
    id: str = Field(default_factory=lambda: _gen_id("cv"))
    summary: str
    vault_path: str | None = None


class DocNode(_BaseNode):
    node_type: Literal[NodeType.DOC] = NodeType.DOC
    id: str = Field(default_factory=lambda: _gen_id("dc"))
    vault_path: str
    title: str


class GateItemNode(_BaseNode):
    node_type: Literal[NodeType.GATE_ITEM] = NodeType.GATE_ITEM
    id: str = Field(default_factory=lambda: _gen_id("g"))
    prompt: str
    urgency: str = "medium"  # urgent | high | medium | novel | low
    resolved_at: datetime | None = None
    decision: str | None = None  # approved | vetoed | resteered
    reasoning: str = ""


class AgentNode(_BaseNode):
    node_type: Literal[NodeType.AGENT] = NodeType.AGENT
    # No id default_factory: agents have stable, externally-configured IDs (from agents.yaml)
    id: str
    role: str  # cto | engineer | pm | writer | inbox | ...
    persona: str
    state: str = "idle"  # idle | working | paused | escalated
    current_firing: str | None = None
    last_active: datetime | None = None
    enabled: bool = True


class EdgeRecord(BaseModel):
    from_id: str
    from_type: NodeType
    to_id: str
    to_type: NodeType
    edge_type: str  # caused-by | led-to | sparred-against | fired-from | etc.
    created_at: datetime = Field(default_factory=_now)
    confidence: float = 1.0


AnyNode = Annotated[
    ThoughtNode
    | BetNode
    | TaskNode
    | DecisionNode
    | ConflictNode
    | OutcomeNode
    | AgentFiringNode
    | CodeChangeNode
    | ConversationNode
    | DocNode
    | GateItemNode
    | AgentNode,
    PydField(discriminator="node_type"),
]
