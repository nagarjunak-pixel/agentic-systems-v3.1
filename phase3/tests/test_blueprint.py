import pytest
import os
import yaml
from codexforge.blueprint import DeclarativeAppBlueprintEngine

def test_blueprint_scaffolding(tmp_path):
    output_dir = tmp_path / "output"
    engine = DeclarativeAppBlueprintEngine(str(output_dir))
    
    # Write a mock YAML blueprint
    blueprint_data = {
        "name": "UserDirectoryApp",
        "roles": ["admin", "editor", "viewer"],
        "models": {
            "User": {
                "fields": {
                    "username": "text",
                    "age": "integer",
                    "is_active": "boolean"
                }
            }
        }
    }
    
    blueprint_file = tmp_path / "blueprint.yaml"
    with open(blueprint_file, "w") as f:
        yaml.safe_dump(blueprint_data, f)
        
    # Scaffold
    res = engine.scaffold_all(str(blueprint_file))
    
    # 1. Check spec parsed
    assert res["spec"]["name"] == "UserDirectoryApp"
    
    # 2. Check DB schema generated
    assert "CREATE TABLE users" in res["schema"]
    assert "username TEXT" in res["schema"]
    assert "age INTEGER" in res["schema"]
    assert "is_active BOOLEAN" in res["schema"]
    assert os.path.exists(output_dir / "schema.sql")
    
    # 3. Check CRUD form generated
    assert "user-form" in res["crud_forms"]["User"]
    assert "input type='checkbox'" in res["crud_forms"]["User"]
    assert os.path.exists(output_dir / "user_form.html")
    
    # 4. Check RBAC stubs
    assert "class RoleBasedAccessController" in res["rbac"]
    assert "['admin', 'editor', 'viewer']" in res["rbac"]
    assert os.path.exists(output_dir / "rbac.py")
    
    # 5. Check blueprint file is marked as immutable context core (Conflict 2)
    assert str(blueprint_file) in engine.immutable_context_files
