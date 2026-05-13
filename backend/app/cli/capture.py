from pathlib import Path

import click
import httpx

from app.config import load_config


@click.command("capture")
@click.argument("content", nargs=-1, required=True)
@click.option(
    "--config",
    envvar="GIGABRAIN_CONFIG",
    default="gigabrain.yaml",
    help="Path to gigabrain.yaml",
)
@click.option(
    "--meta",
    "metas",
    multiple=True,
    help="Metadata key=value pair (can be supplied multiple times).",
)
@click.option(
    "--source",
    default="cli",
    show_default=True,
    help="Override the source field on the capture (default: cli).",
)
def capture_cmd(
    content: tuple[str, ...], config: str, metas: tuple[str, ...], source: str
):
    """Capture a thought into the GigaBrain spine via the configured backend."""
    cfg = load_config(Path(config))
    metadata: dict[str, str] = {}
    for kv in metas:
        if "=" not in kv:
            raise click.BadParameter(f"--meta expects key=value, got: {kv!r}")
        k, v = kv.split("=", 1)
        metadata[k] = v

    payload = {
        "content": " ".join(content),
        "source": source,
        "metadata": metadata,
    }
    url = cfg.capture.backend_url.rstrip("/") + "/capture"
    response = httpx.post(url, json=payload, timeout=cfg.capture.timeout_seconds)
    if response.status_code // 100 != 2:
        raise click.ClickException(
            f"capture failed: {response.status_code} {response.text[:200]}"
        )
    body = response.json()
    click.echo(f"{body['node_id']} ({body['status']})")
