import logging
from datetime import datetime, timezone

from opentelemetry import trace

from app.agents.config import FleetConfig
from app.agents.registry import AgentRegistry
from app.agents.runtime import AgentRuntime
from app.config import LLMConfig
from app.db.edges import EdgeRepository
from app.db.nodes import NodeRepository
from app.db.schemas import AgentFiringNode, EdgeRecord, NodeType
from app.events.bus import EventBus
from app.events.schemas import FireNeuron
from app.telemetry.otel import inject_gigabrain_attrs

log = logging.getLogger(__name__)


class AgentWorker:
    def __init__(
        self,
        *,
        registry: AgentRegistry,
        nodes: NodeRepository,
        edges: EdgeRepository,
        bus: EventBus,
        llm_cfg: LLMConfig,
        fleet: FleetConfig,
        vault_path: str,
        repo_path: str | None,
    ):
        self.registry = registry
        self.nodes = nodes
        self.edges = edges
        self.bus = bus
        self.llm_cfg = llm_cfg
        self.fleet = fleet
        self.vault_path = vault_path
        self.repo_path = repo_path

    def attach(self) -> None:
        self.bus.subscribe("fire.neuron", self._handle_fire_neuron)

    def _mark_firing_complete(self, firing_id: str, outcome: str) -> None:
        self.nodes.conn.query(
            "MATCH (f:AgentFiring) WHERE f.id = $id "
            "SET f.outcome = $outcome, f.completed_at = $completed_at",
            {
                "id": firing_id,
                "outcome": outcome,
                "completed_at": datetime.now(timezone.utc),
            },
        )

    async def _handle_fire_neuron(self, event: FireNeuron) -> None:
        tracer = trace.get_tracer("gigabrain.agents.worker")
        firing_id: str | None = None
        with tracer.start_as_current_span("agent.run") as span:
            inject_gigabrain_attrs(
                span,
                thought_id=event.thought_id,
                agent_role=event.agent_role,
            )
            try:
                agents = self.registry.get_by_role(event.agent_role)
                enabled = [
                    a for a in agents if a.get("enabled") and a.get("state") != "paused"
                ]
                if not enabled:
                    log.warning(
                        "No enabled agents for role %s; dropping firing for thought %s",
                        event.agent_role,
                        event.thought_id,
                    )
                    return
                agent_row = enabled[0]
                agent_id = agent_row["id"]

                spec = next((s for s in self.fleet.agents if s.id == agent_id), None)
                if spec is None:
                    log.warning(
                        "Agent %s in graph but not in fleet config; dropping",
                        agent_id,
                    )
                    return

                inject_gigabrain_attrs(span, agent_id=agent_id)

                firing = AgentFiringNode(
                    agent_id=agent_id,
                    trace_id=f"trace_{event.thought_id}",
                )
                self.nodes.create(firing)
                firing_id = firing.id  # track so the outer except can mark it failed
                inject_gigabrain_attrs(span, firing_id=firing.id)

                self.edges.create(
                    EdgeRecord(
                        from_id=agent_id,
                        from_type=NodeType.AGENT,
                        to_id=firing.id,
                        to_type=NodeType.AGENT_FIRING,
                        edge_type="produced",
                        confidence=1.0,
                    )
                )
                self.edges.create(
                    EdgeRecord(
                        from_id=firing.id,
                        from_type=NodeType.AGENT_FIRING,
                        to_id=event.thought_id,
                        to_type=NodeType.THOUGHT,
                        edge_type="fired-from",
                        confidence=1.0,
                    )
                )

                runtime = AgentRuntime(
                    spec=spec,
                    llm_cfg=self.llm_cfg,
                    vault_path=self.vault_path,
                    repo_path=self.repo_path,
                )
                try:
                    await runtime.run(
                        firing_id=firing.id,
                        task_summary=event.task_summary,
                    )
                    outcome = "success"
                except Exception:
                    log.exception("Agent run failed for firing %s", firing.id)
                    outcome = "failed"

                inject_gigabrain_attrs(span, outcome=outcome)
                self._mark_firing_complete(firing.id, outcome)

            except Exception:
                log.exception(
                    "Worker failed processing fire.neuron for thought %s",
                    event.thought_id,
                )
                if firing_id is not None:
                    # Don't leave the firing node in indeterminate state
                    try:
                        self._mark_firing_complete(firing_id, "failed")
                    except Exception:
                        log.exception("Failed to mark firing %s as failed", firing_id)
