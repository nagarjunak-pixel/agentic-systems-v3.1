from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
import os
import sqlite3
from typing import Dict, Any, List
import sys

# Add dashboards dir to path to import db_helper
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import db_helper

app = FastAPI(title="3D Office Dashboard API")

# Enable CORS so static HTML files can query the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def build_office_data(db_path: str = db_helper.DEFAULT_DB_PATH) -> Dict[str, Any]:
    # Ensure DB is initialized and seeded
    db_helper.seed_db(db_path)
    
    conn = db_helper.get_db_connection(db_path)
    cursor = conn.cursor()
    
    try:
        # Get coordinates
        cursor.execute("SELECT * FROM coordinates_3d")
        coords = [dict(row) for row in cursor.fetchall()]
        
        # Get agent states
        cursor.execute("SELECT * FROM agent_states")
        agents = {row["agent_id"]: dict(row) for row in cursor.fetchall()}
        
        # Get task kanban
        cursor.execute("SELECT * FROM task_kanban")
        tasks = [dict(row) for row in cursor.fetchall()]
        
        desks = []
        
        # Build desks
        for c in coords:
            if c["element_type"] == "desk":
                ref_id = c["associated_ref_id"]
                agent = agents.get(ref_id)
                desk = {
                    "id": c["element_id"],
                    "agent_id": ref_id,
                    "x": c["pos_x"],
                    "y": c["pos_y"],
                    "z": c["pos_z"]
                }
                if agent:
                    desk["agent_name"] = agent["agent_name"]
                    desk["status"] = agent["current_status"]
                    desk["active_task"] = agent["active_task"]
                else:
                    desk["agent_name"] = f"Agent {ref_id}"
                    desk["status"] = "idle"
                    desk["active_task"] = None
                desks.append(desk)
                
        # Build walls (Kanban Boards)
        walls = {
            "backlog": {"id": "wall_backlog", "title": "Backlog", "x": -15.0, "y": 0.0, "z": -15.0, "tasks": []},
            "todo": {"id": "wall_todo", "title": "To Do", "x": -15.0, "y": 0.0, "z": 0.0, "tasks": []},
            "in_progress": {"id": "wall_in_progress", "title": "In Progress", "x": 0.0, "y": 0.0, "z": 15.0, "tasks": []},
            "review": {"id": "wall_review", "title": "Review", "x": 15.0, "y": 0.0, "z": 0.0, "tasks": []},
            "done": {"id": "wall_done", "title": "Done", "x": 15.0, "y": 0.0, "z": -15.0, "tasks": []}
        }
        
        for task in tasks:
            status = task["status"].lower()
            if status in walls:
                walls[status]["tasks"].append({
                    "task_id": task["task_id"],
                    "title": task["title"],
                    "priority": task["priority"],
                    "assigned_agent": task["assigned_agent"]
                })
                
        return {
            "desks": desks,
            "walls": list(walls.values())
        }
        
    finally:
        conn.close()

@app.get("/api/office")
def get_office():
    """Returns the state representing the 3D office layout and taskboards."""
    return build_office_data()

@app.get("/", response_class=HTMLResponse)
def get_index():
    index_path = os.path.join(os.path.dirname(__file__), "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r") as f:
            return f.read()
    return "3D Office UI Viewer HTML not found."
