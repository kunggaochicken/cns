from pathlib import Path

from click.testing import CliRunner

from app.cli.agents import cli


def test_list_agents_command(tmp_path: Path):
    cfg = tmp_path / "gigabrain.yaml"
    cfg.write_text(f"""
db:
  kuzu_path: {tmp_path}/test.kuzu
  vector_path: {tmp_path}/test-vec.sqlite
agents:
  yaml_path: {tmp_path}/agents.yaml
  vault_path: {tmp_path}/vault
""")
    (tmp_path / "agents.yaml").write_text("""
agents:
  - id: eng-1
    role: engineer
    persona: x
""")
    runner = CliRunner()
    result = runner.invoke(cli, ["agents", "--config", str(cfg)])
    if result.exit_code != 0:
        # Surface traceback to help diagnose failures
        print(result.output)
        if result.exception:
            import traceback

            traceback.print_exception(
                type(result.exception), result.exception, result.exception.__traceback__
            )
    assert result.exit_code == 0
    assert "eng-1" in result.output
    assert "engineer" in result.output


def test_list_agents_with_no_fleet(tmp_path: Path):
    cfg = tmp_path / "gigabrain.yaml"
    cfg.write_text(f"""
db:
  kuzu_path: {tmp_path}/test.kuzu
  vector_path: {tmp_path}/test-vec.sqlite
agents:
  yaml_path: {tmp_path}/missing-agents.yaml
  vault_path: {tmp_path}/vault
""")
    runner = CliRunner()
    result = runner.invoke(cli, ["agents", "--config", str(cfg)])
    assert result.exit_code == 0
    assert "no agents" in result.output.lower() or result.output.strip() == ""
