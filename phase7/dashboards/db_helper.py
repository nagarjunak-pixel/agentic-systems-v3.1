import sqlite3
import os
from typing import Dict, Any, List

DEFAULT_DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "shared_core.db"))
SCHEMA_SQL_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "phase0", "db", "schema.sql"))

def get_db_connection(db_path: str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def init_db(db_path: str = DEFAULT_DB_PATH, schema_path: str = SCHEMA_SQL_PATH) -> None:
    """Initializes the database using schema.sql."""
    if not os.path.exists(schema_path):
        raise FileNotFoundError(f"Schema file not found at {schema_path}")
    
    with open(schema_path, "r") as f:
        schema_sql = f.read()
        
    conn = get_db_connection(db_path)
    try:
        conn.executescript(schema_sql)
        conn.commit()
    finally:
        conn.close()

def seed_db(db_path: str = DEFAULT_DB_PATH) -> None:
    """Seeds the database with sample data for demonstration and testing."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    try:
        # Check if already seeded
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='agent_states'")
        if not cursor.fetchone():
            # If tables do not exist, init first
            if db_path == ":memory:":
                with open(SCHEMA_SQL_PATH, "r") as f:
                    schema_sql = f.read()
                conn.executescript(schema_sql)
            else:
                init_db(db_path)
            
        cursor.execute("SELECT COUNT(*) FROM agent_states")
        if cursor.fetchone()[0] > 0:
            return  # Already seeded
        
        # 1. Insert agent states
        agents = [
            ("planner", "Planner Agent", "idle", None),
            ("builder", "Builder Agent", "building", "Build core modules"),
            ("judge", "Judge Agent", "reviewing", "Verify unit tests"),
            ("voice_agent", "Voice Gateway", "idle", None)
        ]
        cursor.executemany(
            "INSERT INTO agent_states (agent_id, agent_name, current_status, active_task) VALUES (?, ?, ?, ?)",
            agents
        )
        
        # 2. Insert task kanban
        tasks = [
            ("t1", "Configure local workspace structures", "done", "high", "builder"),
            ("t2", "Build components and verify functionality", "in_progress", "high", "builder"),
            ("t3", "Verify unit tests", "review", "medium", "judge"),
            ("t4", "Draft marketing copy", "todo", "low", "voice_agent"),
            ("t5", "Create vector store", "backlog", "medium", None)
        ]
        cursor.executemany(
            "INSERT INTO task_kanban (task_id, title, status, priority, assigned_agent) VALUES (?, ?, ?, ?, ?)",
            tasks
        )
        
        # 3. Insert coordinates
        coordinates = [
            ("desk_planner", "desk", -5.0, 0.0, -5.0, "planner"),
            ("desk_builder", "desk", 0.0, 0.0, -5.0, "builder"),
            ("desk_judge", "desk", 5.0, 0.0, -5.0, "judge"),
            ("desk_voice", "desk", 0.0, 0.0, 5.0, "voice_agent"),
            ("node_m1", "node", 1.0, 2.0, 3.0, "t1"),
            ("node_m2", "node", -2.0, 1.5, -1.0, "t2"),
            ("node_m3", "node", 3.0, -1.0, 2.0, "t3"),
            ("node_m4", "node", -4.0, 3.0, -2.0, "t4"),
            ("folder_core", "folder", -2.0, 4.0, -3.0, "planner"),
            ("folder_codex", "folder", 2.0, 4.0, -3.0, "builder")
        ]
        cursor.executemany(
            "INSERT INTO coordinates_3d (element_id, element_type, pos_x, pos_y, pos_z, associated_ref_id) VALUES (?, ?, ?, ?, ?, ?)",
            coordinates
        )
        
        conn.commit()
    finally:
        conn.close()
