from pathlib import Path

import click

from app.agents.config import FleetConfig, load_fleet_config
from app.agents.registry import AgentRegistry
from app.config import load_config
from app.db.kuzu import KuzuConnection
from app.db.nodes import NodeRepository


@click.group()
def cli():
    """GigaBrain CLI."""


@cli.command("agents")
@click.option(
    "--config",
    envvar="GIGABRAIN_CONFIG",
    default="gigabrain.yaml",
    help="Path to gigabrain.yaml",
)
def list_agents(config: str):
    """List the configured agent fleet and their current state."""
    cfg = load_config(Path(config))
    conn = KuzuConnection(cfg.db.kuzu_path)
    conn.connect()
    schema_dir = Path(__file__).parents[2] / "kuzu_schema"
    conn.bootstrap_schema(schema_dir)
    nodes = NodeRepository(conn)
    reg = AgentRegistry(nodes=nodes, conn=conn)

    # If a fleet yaml exists, sync first so the graph reflects the file
    fleet_path = Path(cfg.agents.yaml_path)
    if fleet_path.exists():
        fleet = load_fleet_config(fleet_path)
        reg.sync(fleet)
    else:
        fleet = FleetConfig()

    rows = reg.list_agents()
    if not rows:
        click.echo(f"(no agents — check agents.yaml at {cfg.agents.yaml_path})")
        conn.close()
        return
    for row in rows:
        state = row.get("state") or "idle"
        enabled = "enabled" if row.get("enabled", True) else "disabled"
        click.echo(f"{row['id']:<10} {row['role']:<10} {state:<8} {enabled}")
    conn.close()


if __name__ == "__main__":
    cli()
