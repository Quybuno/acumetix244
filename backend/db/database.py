"""
Database Manager for Deep Review Backend (Phase 3 - Task T3.1)
Handles SQLite connection pooling, table initialization, and schema inspection.
"""

import sqlite3
import os
from pathlib import Path
from typing import Optional, List, Dict, Any
from backend.db.schema import CREATE_TABLES_SQL, FORBIDDEN_COLUMN_SUBSTRINGS

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "deepreview.db"

class Database:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = str(db_path) if db_path else str(DEFAULT_DB_PATH)
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None

    def get_connection(self) -> sqlite3.Connection:
        if self._conn is None or self.db_path != ":memory:":
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON;")
            if self.db_path == ":memory:":
                self._conn = conn
            return conn
        return self._conn

    def init_schema(self):
        """Initialize all database tables and indexes."""
        conn = self.get_connection()
        try:
            conn.executescript(CREATE_TABLES_SQL)
            conn.commit()
        finally:
            if self.db_path != ":memory:":
                conn.close()

    def get_all_columns(self) -> Dict[str, List[str]]:
        """
        Inspect SQLite catalog and return a mapping of table_name -> [column_names].
        Used to strictly verify that no table contains secret columns.
        """
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
            tables = [row[0] for row in cursor.fetchall()]
            
            table_columns = {}
            for table in tables:
                cursor.execute(f"PRAGMA table_info({table});")
                cols = [row["name"] for row in cursor.fetchall()]
                table_columns[table] = cols
            return table_columns
        finally:
            if self.db_path != ":memory:":
                conn.close()

    def verify_zero_secret_columns(self) -> bool:
        """
        Enforce that NO column in any table contains sensitive substrings.
        Raises AssertionError if any forbidden column is found.
        """
        table_columns = self.get_all_columns()
        for table, cols in table_columns.items():
            for col in cols:
                col_lower = col.lower()
                for forbidden in FORBIDDEN_COLUMN_SUBSTRINGS:
                    if forbidden in col_lower:
                        raise AssertionError(
                            f"SECURITY VIOLATION: Column '{col}' in table '{table}' "
                            f"violates zero-secret constraint (matched forbidden keyword '{forbidden}')."
                        )
        return True
