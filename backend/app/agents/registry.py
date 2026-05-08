from app.agents.config import FleetConfig
from app.db.kuzu import KuzuConnection
from app.db.nodes import NodeRepository
from app.db.schemas import AgentNode


class AgentRegistry:
    def __init__(self, *, nodes: NodeRepository, conn: KuzuConnection):
        self.nodes = nodes
        self.conn = conn

    def sync(self, fleet: FleetConfig) -> None:
        """Idempotent: create-or-update each AgentSpec as an AgentNode."""
        for spec in fleet.agents:
            existing = self.nodes.get(spec.id, "Agent")
            if existing is None:
                self.nodes.create(
                    AgentNode(
                        id=spec.id,
                        role=spec.role,
                        persona=spec.persona,
                        enabled=spec.enabled,
                    )
                )
            else:
                self.conn.query(
                    "MATCH (a:Agent) WHERE a.id = $id "
                    "SET a.role = $role, a.persona = $persona, a.enabled = $enabled",
                    {
                        "id": spec.id,
                        "role": spec.role,
                        "persona": spec.persona,
                        "enabled": spec.enabled,
                    },
                )

    def list_agents(self) -> list[dict]:
        return self.conn.query(
            "MATCH (a:Agent) RETURN a.id AS id, a.role AS role, "
            "a.persona AS persona, a.state AS state, a.enabled AS enabled, "
            "a.last_active AS last_active"
        )

    def get_by_id(self, agent_id: str) -> dict | None:
        return self.nodes.get(agent_id, "Agent")

    def get_by_role(self, role: str) -> list[dict]:
        return self.conn.query(
            "MATCH (a:Agent) WHERE a.role = $role RETURN a.id AS id, "
            "a.role AS role, a.persona AS persona, a.state AS state, "
            "a.enabled AS enabled",
            {"role": role},
        )
