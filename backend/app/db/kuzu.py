from pathlib import Path
from typing import Any

import kuzu


class KuzuConnection:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._db: kuzu.Database | None = None
        self._conn: kuzu.Connection | None = None

    def connect(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db = kuzu.Database(self.db_path)
        self._conn = kuzu.Connection(self._db)

    def close(self) -> None:
        self._conn = None
        self._db = None

    def query(self, cypher: str, params: dict[str, Any] | None = None) -> list[dict]:
        if self._conn is None:
            raise RuntimeError("Not connected")
        result = self._conn.execute(cypher, parameters=params or {})
        col_names = result.get_column_names()
        rows = []
        while result.has_next():
            row = result.get_next()
            rows.append(dict(zip(col_names, row, strict=True)))
        return rows

    def bootstrap_schema(self, schema_dir: Path | str) -> None:
        if self._conn is None:
            raise RuntimeError("Not connected")
        schema_dir = Path(schema_dir)
        for cypher_file in sorted(schema_dir.glob("*.cypher")):
            text = cypher_file.read_text()
            # Strip whole-line // comments before splitting on ;
            cleaned = "\n".join(
                line for line in text.splitlines() if not line.lstrip().startswith("//")
            )
            for stmt in (s.strip() for s in cleaned.split(";") if s.strip()):
                self._conn.execute(stmt)
