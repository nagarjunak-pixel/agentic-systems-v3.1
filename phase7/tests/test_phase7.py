import os
import sqlite3
import pytest
from fastapi.testclient import TestClient
import sys

# Add path mapping for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
phase7_dir = os.path.abspath(os.path.join(current_dir, ".."))
if phase7_dir not in sys.path:
    sys.path.insert(0, phase7_dir)

from dashboards import db_helper
from dashboards.memory_galaxy.api import app as memory_galaxy_app, build_graph_data
from dashboards.office.api import app as office_app, build_office_data
from orchestrator_glue import SystemStatus

# Temp DB path for testing
TEST_DB_PATH = "test_shared_core.db"

@pytest.fixture
def setup_test_db():
    """Fixture to set up a temporary file database with schema and seed data."""
    schema_path = os.path.abspath(os.path.join(current_dir, "../../phase0/db/schema.sql"))
    
    if os.path.exists(TEST_DB_PATH):
        try:
            os.remove(TEST_DB_PATH)
        except Exception:
            pass
            
    db_helper.init_db(TEST_DB_PATH, schema_path)
    db_helper.seed_db(TEST_DB_PATH)
    
    yield TEST_DB_PATH
    
    if os.path.exists(TEST_DB_PATH):
        try:
            os.remove(TEST_DB_PATH)
        except Exception:
            pass

# 1. Memory Galaxy Tests
def test_db_init_and_seed(setup_test_db):
    """Test that DB init creates tables and seeding works."""
    conn = db_helper.get_db_connection(TEST_DB_PATH)
    cursor = conn.cursor()
    
    # Verify tables exist
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row["name"] for row in cursor.fetchall()]
    assert "agent_states" in tables
    assert "task_kanban" in tables
    assert "coordinates_3d" in tables
    
    # Verify records exist
    cursor.execute("SELECT COUNT(*) FROM agent_states")
    assert cursor.fetchone()[0] > 0
    cursor.execute("SELECT COUNT(*) FROM task_kanban")
    assert cursor.fetchone()[0] > 0
    cursor.execute("SELECT COUNT(*) FROM coordinates_3d")
    assert cursor.fetchone()[0] > 0
    conn.close()

def test_graph_builder_produces_nodes_edges(setup_test_db):
    """Test that graph builder produces nodes and edges from seed data."""
    graph = build_graph_data(TEST_DB_PATH)
    
    assert "nodes" in graph
    assert "links" in graph
    
    nodes = graph["nodes"]
    links = graph["links"]
    
    assert len(nodes) > 0
    assert len(links) > 0
    
    # Verify desk node details are enriched
    desk_node = next((n for n in nodes if n["type"] == "desk"), None)
    assert desk_node is not None
    assert "label" in desk_node
    assert "status" in desk_node
    
    # Verify folder node details
    folder_node = next((n for n in nodes if n["type"] == "folder"), None)
    assert folder_node is not None
    assert "label" in folder_node
    
    # Verify link mapping
    assigned_link = next((l for l in links if l["type"] == "assigned_to"), None)
    assert assigned_link is not None

def test_memory_galaxy_api_returns_valid_json(setup_test_db):
    """Test Memory Galaxy API endpoints using TestClient."""
    from dashboards.memory_galaxy import api
    original_db = api.db_helper.DEFAULT_DB_PATH
    api.db_helper.DEFAULT_DB_PATH = TEST_DB_PATH
    
    try:
        client = TestClient(memory_galaxy_app)
        response = client.get("/api/graph")
        assert response.status_code == 200
        data = response.json()
        assert "nodes" in data
        assert "links" in data
    finally:
        api.db_helper.DEFAULT_DB_PATH = original_db

# 2. Office Dashboard Tests
def test_office_layout_mapping(setup_test_db):
    """Test that kanban state and agent state map correctly to office layout."""
    office = build_office_data(TEST_DB_PATH)
    
    assert "desks" in office
    assert "walls" in office
    
    desks = office["desks"]
    walls = office["walls"]
    
    assert len(desks) > 0
    assert len(walls) == 5  # backlog, todo, in_progress, review, done
    
    # Check a desk
    builder_desk = next((d for d in desks if d["agent_id"] == "builder"), None)
    assert builder_desk is not None
    assert builder_desk["status"] == "building"
    assert builder_desk["active_task"] == "Build core modules"
    
    # Check that wall contains tasks
    in_progress_wall = next((w for w in walls if w["title"] == "In Progress"), None)
    assert in_progress_wall is not None
    assert len(in_progress_wall["tasks"]) > 0
    assert in_progress_wall["tasks"][0]["assigned_agent"] == "builder"

def test_office_api_returns_valid_json(setup_test_db):
    """Test Office API endpoint returns valid JSON."""
    from dashboards.office import api
    original_db = api.db_helper.DEFAULT_DB_PATH
    api.db_helper.DEFAULT_DB_PATH = TEST_DB_PATH
    
    try:
        client = TestClient(office_app)
        response = client.get("/api/office")
        assert response.status_code == 200
        data = response.json()
        assert "desks" in data
        assert "walls" in data
    finally:
        api.db_helper.DEFAULT_DB_PATH = original_db

# 3. Orchestrator Glue Tests
def test_orchestrator_glue_aggregator():
    """Test SystemStatus aggregator when mocking subsystems."""
    # 1. Full mock mode
    aggregator = SystemStatus()
    status = aggregator.aggregate_status()
    
    assert status["status"] == "HEALTHY"
    assert "orchestrator" in status["subsystems"]
    assert "abtm" in status["subsystems"]
    assert "aisg" in status["subsystems"]
    assert "voice_gateway" in status["subsystems"]
    
    # 2. Check degraded state on budget exceeded mock
    class MockBudgetManager:
        def __init__(self):
            self.global_limit = 1000
            self.global_usage = 1200
            self.agent_usage = {}

    budget_mock = MockBudgetManager()
    aggregator_degraded = SystemStatus(budget_manager=budget_mock)
    status_degraded = aggregator_degraded.aggregate_status()
    
    assert status_degraded["status"] == "DEGRADED"
    assert status_degraded["subsystems"]["abtm"]["status"] == "BUDGET_EXCEEDED"
