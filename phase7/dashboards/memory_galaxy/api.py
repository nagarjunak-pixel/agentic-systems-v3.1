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

app = FastAPI(title="Memory Galaxy API")

# Enable CORS so static HTML files can query the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def build_graph_data(db_path: str = db_helper.DEFAULT_DB_PATH) -> Dict[str, Any]:
    # Ensure DB is initialized and seeded
    db_helper.seed_db(db_path)
    
    conn = db_helper.get_db_connection(db_path)
    cursor = conn.cursor()
    
    try:
        # Check coordinates table
        cursor.execute("SELECT * FROM coordinates_3d")
        coords = [dict(row) for row in cursor.fetchall()]
        
        # Get agent states
        cursor.execute("SELECT * FROM agent_states")
        agents = {row["agent_id"]: dict(row) for row in cursor.fetchall()}
        
        # Get task kanban
        cursor.execute("SELECT * FROM task_kanban")
        tasks = {row["task_id"]: dict(row) for row in cursor.fetchall()}
        
        nodes = []
        links = []
        
        # Build Nodes
        for c in coords:
            ref_id = c["associated_ref_id"]
            node_id = c["element_id"]
            node_type = c["element_type"]
            
            node = {
                "id": node_id,
                "type": node_type,
                "x": c["pos_x"],
                "y": c["pos_y"],
                "z": c["pos_z"],
                "ref_id": ref_id
            }
            
            if node_type == "desk":
                agent = agents.get(ref_id)
                if agent:
                    node["label"] = agent["agent_name"]
                    node["status"] = agent["current_status"]
                    node["active_task"] = agent["active_task"]
                else:
                    node["label"] = f"Agent {ref_id}"
            elif node_type == "node":
                task = tasks.get(ref_id)
                if task:
                    node["label"] = task["title"]
                    node["status"] = task["status"]
                    node["priority"] = task["priority"]
                    node["assigned_agent"] = task["assigned_agent"]
                else:
                    node["label"] = f"Memory {ref_id}"
            elif node_type == "folder":
                node["label"] = f"Folder: {ref_id}"
                
            nodes.append(node)
            
        # Build Edges/Links
        # 1. Links between tasks (node) and assigned agents (desk)
        # 2. Links from agents (desk) to their associated folder/projects
        for node in nodes:
            if node["type"] == "node" and "assigned_agent" in node and node["assigned_agent"]:
                # Find the desk of this agent
                assigned_agent_id = node["assigned_agent"]
                desk_node = next((n for n in nodes if n["type"] == "desk" and n["ref_id"] == assigned_agent_id), None)
                if desk_node:
                    links.append({
                        "source": desk_node["id"],
                        "target": node["id"],
                        "type": "assigned_to"
                    })
            
            if node["type"] == "folder":
                # Folders link to the agents (desks) associated with them
                assoc_agent_id = node["ref_id"]
                desk_node = next((n for n in nodes if n["type"] == "desk" and n["ref_id"] == assoc_agent_id), None)
                if desk_node:
                    links.append({
                        "source": desk_node["id"],
                        "target": node["id"],
                        "type": "project_owner"
                    })
                    
        return {"nodes": nodes, "links": links}
        
    finally:
        conn.close()

@app.get("/api/graph")
def get_graph():
    """Returns the graph structure representing the memory galaxy."""
    return build_graph_data()

@app.get("/", response_class=HTMLResponse)
def get_index():
    index_path = os.path.join(os.path.dirname(__file__), "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r") as f:
            return f.read()
    return "Memory Galaxy UI Viewer HTML not found."
