-- Shared central database schema for states, briefs, and dashboard layouts (Conflict 4 Resolution)

CREATE TABLE IF NOT EXISTS agent_states (
    agent_id VARCHAR(64) PRIMARY KEY,
    agent_name VARCHAR(128) NOT NULL,
    current_status VARCHAR(64) NOT NULL, -- 'planning', 'building', 'reviewing', 'idle'
    active_task VARCHAR(256),
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS task_kanban (
    task_id VARCHAR(64) PRIMARY KEY,
    title VARCHAR(256) NOT NULL,
    status VARCHAR(64) NOT NULL, -- 'backlog', 'todo', 'in_progress', 'review', 'done'
    priority VARCHAR(32) DEFAULT 'medium',
    assigned_agent VARCHAR(64) REFERENCES agent_states(agent_id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS coordinates_3d (
    element_id VARCHAR(64) PRIMARY KEY,
    element_type VARCHAR(64) NOT NULL, -- 'desk', 'node', 'folder'
    pos_x FLOAT NOT NULL,
    pos_y FLOAT NOT NULL,
    pos_z FLOAT NOT NULL,
    associated_ref_id VARCHAR(64) NOT NULL -- Links to task_id or agent_id
);
