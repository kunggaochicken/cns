from unittest.mock import MagicMock, patch

from click.testing import CliRunner


def test_capture_posts_thought_to_backend(tmp_path):
    from app.cli.agents import cli

    cfg_path = tmp_path / "g.yaml"
    cfg_path.write_text(
        "capture:\n  backend_url: http://localhost:9999\n  timeout_seconds: 2.0\n"
    )

    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {"node_id": "t_abc123", "status": "sparring"}

    with patch("app.cli.capture.httpx.post", return_value=fake_response) as mock_post:
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["capture", "should we ship preview?", "--config", str(cfg_path)],
        )

    assert result.exit_code == 0, result.output
    assert "t_abc123" in result.output
    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    assert args[0] == "http://localhost:9999/capture"
    assert kwargs["json"]["content"] == "should we ship preview?"
    assert kwargs["json"]["source"] == "cli"
    assert kwargs["timeout"] == 2.0


def test_capture_passes_metadata_from_flag(tmp_path):
    from app.cli.agents import cli

    cfg_path = tmp_path / "g.yaml"
    cfg_path.write_text("capture:\n  backend_url: http://localhost:9999\n")

    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {"node_id": "t_xyz", "status": "sparring"}

    with patch("app.cli.capture.httpx.post", return_value=fake_response) as mock_post:
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "capture",
                "hello",
                "--config",
                str(cfg_path),
                "--meta",
                "ticket=GIG-42",
                "--meta",
                "channel=#brain",
            ],
        )

    assert result.exit_code == 0, result.output
    _, kwargs = mock_post.call_args
    assert kwargs["json"]["metadata"] == {"ticket": "GIG-42", "channel": "#brain"}


def test_capture_non_2xx_exits_nonzero_and_prints_error(tmp_path):
    from app.cli.agents import cli

    cfg_path = tmp_path / "g.yaml"
    cfg_path.write_text("capture:\n  backend_url: http://localhost:9999\n")

    fake_response = MagicMock()
    fake_response.status_code = 500
    fake_response.text = "internal error"

    with patch("app.cli.capture.httpx.post", return_value=fake_response):
        runner = CliRunner()
        result = runner.invoke(cli, ["capture", "broken", "--config", str(cfg_path)])

    assert result.exit_code != 0
    assert "500" in result.output or "error" in result.output.lower()


def test_capture_against_real_capture_router(tmp_path, monkeypatch):
    """End-to-end: CLI -> in-process FastAPI app -> /capture writes a thought.

    Uses TestClient (which already speaks ASGI) by monkey-patching httpx.post
    on the CLI module to dispatch through it, so we don't need a network port.
    """
    from pathlib import Path
    from unittest.mock import AsyncMock

    from click.testing import CliRunner
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.capture.api import build_capture_router
    from app.cli import capture as capture_module
    from app.cli.agents import cli
    from app.db.kuzu import KuzuConnection
    from app.db.nodes import NodeRepository
    from app.db.vector import VectorStore
    from app.events.bus import EventBus

    conn = KuzuConnection(str(tmp_path / "t.kuzu"))
    conn.connect()
    schema_dir = Path(__file__).parents[2] / "kuzu_schema"
    conn.bootstrap_schema(schema_dir)
    nodes = NodeRepository(conn)
    vec = VectorStore(str(tmp_path / "v.sqlite"), dim=4)
    vec.connect()
    embedder = AsyncMock()
    embedder.embed.return_value = [0.1, 0.2, 0.3, 0.4]
    embedder.dim = 4

    app = FastAPI()
    app.include_router(
        build_capture_router(nodes=nodes, vec=vec, bus=EventBus(), embedder=embedder)
    )

    test_client = TestClient(app)

    def _post(url, **kwargs):
        # Rewrite the URL to just the path so TestClient handles it in-process.
        path = "/" + url.split("://", 1)[1].split("/", 1)[1]
        # TestClient's post doesn't accept `timeout`; drop it.
        kwargs.pop("timeout", None)
        return test_client.post(path, **kwargs)

    monkeypatch.setattr(capture_module.httpx, "post", _post)

    cfg_path = tmp_path / "g.yaml"
    cfg_path.write_text("capture:\n  backend_url: http://testserver\n")

    runner = CliRunner()
    result = runner.invoke(cli, ["capture", "smoke", "--config", str(cfg_path)])
    assert result.exit_code == 0, result.output
    assert "(sparring)" in result.output

    vec.close()
    conn.close()
