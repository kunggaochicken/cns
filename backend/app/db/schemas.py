from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated
from uuid import uuid4

from pydantic import BaseModel, Field


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

    @property
    def node_type(self) -> NodeType:
        raise NotImplementedError


class ThoughtNode(_BaseNode):
    id: str = Field(default_factory=lambda: _gen_id("t"))
    content: str
    source: str  # pwa | voice | web | cli | obsidian | linear | github
    metadata: dict = Field(default_factory=dict)

    @property
    def node_type(self) -> NodeType:
        return NodeType.THOUGHT


class BetNode(_BaseNode):
    id: str = Field(default_factory=lambda: _gen_id("b"))
    slug: str
    title: str
    vault_path: str
    owner: str
    horizon: str = "Q"
    confidence: str = "medium"

    @property
    def node_type(self) -> NodeType:
        return NodeType.BET


class TaskNode(_BaseNode):
    id: str = Field(default_factory=lambda: _gen_id("k"))
    linear_id: str
    title: str
    status: str = "todo"

    @property
    def node_type(self) -> NodeType:
        return NodeType.TASK


class DecisionNode(_BaseNode):
    id: str = Field(default_factory=lambda: _gen_id("d"))
    content: str
    decided_by: str
    reasoning: str = ""

    @property
    def node_type(self) -> NodeType:
        return NodeType.DECISION


class ConflictNode(_BaseNode):
    id: str = Field(default_factory=lambda: _gen_id("c"))
    summary: str
    severity: str = "medium"

    @property
    def node_type(self) -> NodeType:
        return NodeType.CONFLICT


class OutcomeNode(_BaseNode):
    id: str = Field(default_factory=lambda: _gen_id("o"))
    summary: str
    success: bool

    @property
    def node_type(self) -> NodeType:
        return NodeType.OUTCOME


class AgentFiringNode(_BaseNode):
    id: str = Field(default_factory=lambda: _gen_id("f"))
    agent_id: str
    trace_id: str
    started_at: datetime = Field(default_factory=_now)
    completed_at: datetime | None = None
    outcome: str | None = None  # success | partial | failed

    @property
    def node_type(self) -> NodeType:
        return NodeType.AGENT_FIRING


class CodeChangeNode(_BaseNode):
    id: str = Field(default_factory=lambda: _gen_id("cc"))
    repo: str
    sha: str
    summary: str

    @property
    def node_type(self) -> NodeType:
        return NodeType.CODE_CHANGE


class ConversationNode(_BaseNode):
    id: str = Field(default_factory=lambda: _gen_id("cv"))
    summary: str
    vault_path: str | None = None

    @property
    def node_type(self) -> NodeType:
        return NodeType.CONVERSATION


class DocNode(_BaseNode):
    id: str = Field(default_factory=lambda: _gen_id("dc"))
    vault_path: str
    title: str

    @property
    def node_type(self) -> NodeType:
        return NodeType.DOC


class GateItemNode(_BaseNode):
    id: str = Field(default_factory=lambda: _gen_id("g"))
    prompt: str
    urgency: str = "medium"  # urgent | medium | novel
    resolved_at: datetime | None = None
    decision: str | None = None  # approved | vetoed | resteered
    reasoning: str = ""

    @property
    def node_type(self) -> NodeType:
        return NodeType.GATE_ITEM


class AgentNode(_BaseNode):
    id: str
    role: str  # cto | engineer | pm | writer | inbox | ...
    persona: str
    state: str = "idle"  # idle | working | paused | escalated
    current_firing: str | None = None
    last_active: datetime | None = None

    @property
    def node_type(self) -> NodeType:
        return NodeType.AGENT


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
    "any node type",
]
