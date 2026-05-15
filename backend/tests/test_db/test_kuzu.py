from pathlib import Path

from app.db.kuzu import KuzuConnection


def test_connect_creates_db_file(tmp_path: Path):
    db_path = tmp_path / "test.kuzu"
    conn = KuzuConnection(str(db_path))
    conn.connect()
    assert db_path.exists()
    conn.close()


def test_bootstrap_schema_creates_node_tables(tmp_path: Path):
    db_path = tmp_path / "test.kuzu"
    conn = KuzuConnection(str(db_path))
    conn.connect()
    schema_dir = Path(__file__).parents[2] / "kuzu_schema"
    conn.bootstrap_schema(schema_dir)
    result = conn.query("CALL show_tables() RETURN *;")
    table_names = {row["name"] for row in result}
    expected = {
        "Thought",
        "Bet",
        "Task",
        "Decision",
        "Conflict",
        "Outcome",
        "AgentFiring",
        "CodeChange",
        "Conversation",
        "Doc",
        "GateItem",
        "Agent",
    }
    assert expected.issubset(table_names)
    conn.close()


def test_bootstrap_checkpoints_schema_into_main_file(tmp_path: Path):
    # After bootstrap, the schema DDL must be flushed into the main .kuzu file
    # (not left only in the WAL). We verify by reopening with the WAL deleted:
    # the tables must still be there.
    db_path = tmp_path / "test.kuzu"
    conn = KuzuConnection(str(db_path))
    conn.connect()
    conn.bootstrap_schema(Path(__file__).parents[2] / "kuzu_schema")
    conn.close()

    wal = tmp_path / "test.kuzu.wal"
    if wal.exists():
        wal.unlink()

    reopened = KuzuConnection(str(db_path))
    reopened.connect()
    names = {r["name"] for r in reopened.query("CALL show_tables() RETURN *;")}
    assert "Thought" in names
    reopened.close()
