import logging
from datetime import datetime, timezone

from app.agents.config import FleetConfig
from app.agents.registry import AgentRegistry
from app.agents.runtime import AgentRuntime
from app.config import LLMConfig
from app.db.edges import EdgeRepository
from app.db.nodes import NodeRepository
from app.db.schemas import AgentFiringNode, EdgeRecord, NodeType
from app.events.bus import EventBus
from app.events.schemas import FireNeuron

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

    async def _handle_fire_neuron(self, event: FireNeuron) -> None:
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

            firing = AgentFiringNode(
                agent_id=agent_id,
                trace_id=f"trace_{event.thought_id}",
            )
            self.nodes.create(firing)
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

            self.nodes.conn.query(
                "MATCH (f:AgentFiring) WHERE f.id = $id "
                "SET f.outcome = $outcome, f.completed_at = $completed_at",
                {
                    "id": firing.id,
                    "outcome": outcome,
                    "completed_at": datetime.now(timezone.utc),
                },
            )
        except Exception:
            log.exception(
                "Worker failed processing fire.neuron for thought %s",
                event.thought_id,
            )
