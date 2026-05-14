from pathlib import Path

import pytest
from pydantic import ValidationError

from app.agents.config import FleetConfig, load_fleet_config


def test_load_fleet_from_yaml(tmp_path: Path):
    cfg_file = tmp_path / "agents.yaml"
    cfg_file.write_text(
        """
agents:
  - id: cto-1
    role: cto
    persona: Senior CTO. Architecture decisions only.
    enabled: true
    tools:
      - vault_read
      - run_tests
    escalates_to: null

  - id: engineer-1
    role: engineer
    persona: Drafts code, runs tests, stages commits.
    enabled: true
    tools:
      - vault_read
      - vault_write
      - run_tests
      - stage_commits
    escalates_to: cto-1
        """
    )
    fleet = load_fleet_config(cfg_file)
    assert isinstance(fleet, FleetConfig)
    assert len(fleet.agents) == 2
    assert fleet.agents[0].id == "cto-1"
    assert "stage_commits" in fleet.agents[1].tools
    assert fleet.agents[1].escalates_to == "cto-1"


def test_load_fleet_missing_file_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        load_fleet_config(tmp_path / "missing.yaml")


def test_agent_id_must_be_unique(tmp_path: Path):
    cfg_file = tmp_path / "agents.yaml"
    cfg_file.write_text(
        """
agents:
  - id: dup
    role: cto
    persona: a
    tools: []
  - id: dup
    role: engineer
    persona: b
    tools: []
        """
    )
    with pytest.raises(ValueError, match="duplicate agent id"):
        load_fleet_config(cfg_file)


def test_fleet_config_defaults_dispatch_max_parallel_to_one(tmp_path):
    p = tmp_path / "f.yaml"
    p.write_text("agents: []\n")
    fleet = load_fleet_config(p)
    assert fleet.dispatch.max_parallel == 1
    assert fleet.dispatch.per_role == {}


def test_fleet_config_parses_dispatch_block(tmp_path):
    p = tmp_path / "f.yaml"
    p.write_text(
        "agents: []\n"
        "dispatch:\n"
        "  max_parallel: 3\n"
        "  per_role:\n"
        "    cto: 1\n"
        "    engineer: 2\n"
    )
    fleet = load_fleet_config(p)
    assert fleet.dispatch.max_parallel == 3
    assert fleet.dispatch.per_role == {"cto": 1, "engineer": 2}


def test_fleet_config_rejects_max_parallel_below_one(tmp_path):
    p = tmp_path / "f.yaml"
    p.write_text("agents: []\ndispatch:\n  max_parallel: 0\n")
    with pytest.raises(ValidationError):
        load_fleet_config(p)


def test_fleet_config_rejects_per_role_value_below_one(tmp_path):
    p = tmp_path / "f.yaml"
    p.write_text("agents: []\ndispatch:\n  max_parallel: 3\n  per_role:\n    cto: 0\n")
    with pytest.raises(ValidationError):
        load_fleet_config(p)
