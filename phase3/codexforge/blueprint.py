import os
import yaml
import logging
from typing import Dict, Any, List

logger = logging.getLogger("CodexForge.BlueprintEngine")

class DeclarativeAppBlueprintEngine:
    def __init__(self, output_dir: str):
        self.output_dir = os.path.abspath(output_dir)
        os.makedirs(self.output_dir, exist_ok=True)
        # Conflict 2: Immutable context cores list
        self.immutable_context_files = set()

    def mark_immutable_context_core(self, file_path: str):
        """
        Designates blueprint YAML/Markdown files as 'immutable context cores'
        which must not be pruned/compressed by token optimization algorithms (Conflict 2 fix).
        """
        abs_path = os.path.abspath(file_path)
        self.immutable_context_files.add(abs_path)
        logger.info(f"Marked as immutable context core: {abs_path}")

    def parse_blueprint(self, file_path: str) -> Dict[str, Any]:
        """
        Parses YAML or Markdown application specifications.
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Blueprint file not found: {file_path}")

        # Mark it as immutable context core automatically when parsed
        self.mark_immutable_context_core(file_path)

        with open(file_path, "r") as f:
            content = f.read()

        if file_path.endswith((".yaml", ".yml")):
            try:
                return yaml.safe_load(content)
            except Exception as e:
                raise ValueError(f"Failed to parse YAML blueprint: {e}")
        else:
            # Simple markdown parsing (fallback)
            return self._parse_markdown_spec(content)

    def _parse_markdown_spec(self, markdown_content: str) -> Dict[str, Any]:
        """Rudimentary markdown spec parser looking for tables or list blocks."""
        spec = {"name": "MarkdownApp", "models": {}}
        current_model = None
        
        for line in markdown_content.split("\n"):
            line = line.strip()
            if line.startswith("# "):
                spec["name"] = line[2:].strip()
            elif line.startswith("## Model:"):
                current_model = line[9:].strip()
                spec["models"][current_model] = {"fields": {}}
            elif line.startswith("- ") and ":" in line and current_model:
                parts = line[2:].split(":", 1)
                field_name = parts[0].strip()
                field_type = parts[1].strip()
                spec["models"][current_model]["fields"][field_name] = field_type
                
        return spec

    def generate_db_schema(self, spec: Dict[str, Any]) -> str:
        """Generates SQL DB schemas from spec."""
        sql_lines = []
        for model_name, model_info in spec.get("models", {}).items():
            sql_lines.append(f"CREATE TABLE {model_name.lower()}s (")
            sql_lines.append("    id INTEGER PRIMARY KEY AUTOINCREMENT,")
            
            fields = model_info.get("fields", {})
            field_definitions = []
            for field_name, field_type in fields.items():
                sql_type = "TEXT"
                ft_lower = field_type.lower()
                if "int" in ft_lower:
                    sql_type = "INTEGER"
                elif "float" in ft_lower or "double" in ft_lower or "number" in ft_lower:
                    sql_type = "REAL"
                elif "bool" in ft_lower:
                    sql_type = "BOOLEAN"
                elif "date" in ft_lower or "time" in ft_lower:
                    sql_type = "TIMESTAMP"
                field_definitions.append(f"    {field_name} {sql_type}")
                
            sql_lines.append(",\n".join(field_definitions))
            sql_lines.append(");\n")
            
        schema = "\n".join(sql_lines)
        schema_path = os.path.join(self.output_dir, "schema.sql")
        with open(schema_path, "w") as f:
            f.write(schema)
        logger.info(f"Generated SQL schema to {schema_path}")
        return schema

    def generate_crud_forms(self, spec: Dict[str, Any]) -> Dict[str, str]:
        """Generates mock HTML/JS CRUD form stubs."""
        forms = {}
        for model_name, model_info in spec.get("models", {}).items():
            form_html = [f"<form id='{model_name.lower()}-form'>"]
            form_html.append(f"    <h3>Create {model_name}</h3>")
            
            for field_name, field_type in model_info.get("fields", {}).items():
                input_type = "text"
                ft_lower = field_type.lower()
                if "int" in ft_lower or "real" in ft_lower:
                    input_type = "number"
                elif "bool" in ft_lower:
                    input_type = "checkbox"
                elif "date" in ft_lower:
                    input_type = "date"
                    
                form_html.append(f"    <div class='form-group'>")
                form_html.append(f"        <label for='{field_name}'>{field_name.capitalize()}</label>")
                if input_type == "checkbox":
                    form_html.append(f"        <input type='checkbox' id='{field_name}' name='{field_name}' />")
                else:
                    form_html.append(f"        <input type='{input_type}' id='{field_name}' name='{field_name}' required />")
                form_html.append(f"    </div>")
                
            form_html.append("    <button type='submit'>Submit</button>")
            form_html.append("</form>")
            
            form_content = "\n".join(form_html)
            forms[model_name] = form_content
            
            form_path = os.path.join(self.output_dir, f"{model_name.lower()}_form.html")
            with open(form_path, "w") as f:
                f.write(form_content)
                
        logger.info(f"Generated CRUD forms for models: {list(forms.keys())}")
        return forms

    def generate_rbac_stubs(self, spec: Dict[str, Any]) -> str:
        """Generates RBAC policy stubs based on roles defined in spec."""
        roles = spec.get("roles", ["admin", "user"])
        rbac_lines = [
            "class RoleBasedAccessController:",
            "    def __init__(self):",
            f"        self.allowed_roles = {roles}",
            "",
            "    def check_permission(self, user_role: str, action: str) -> bool:",
            "        if user_role not in self.allowed_roles:",
            "            return False",
            "        if user_role == 'admin':",
            "            return True",
            "        # Standard user permissions",
            "        if user_role == 'user' and action in ['read', 'create']:",
            "            return True",
            "        return False"
        ]
        rbac_content = "\n".join(rbac_lines)
        rbac_path = os.path.join(self.output_dir, "rbac.py")
        with open(rbac_path, "w") as f:
            f.write(rbac_content)
        logger.info(f"Generated RBAC stubs to {rbac_path}")
        return rbac_content

    def scaffold_all(self, blueprint_file: str) -> Dict[str, Any]:
        """Scaffolds complete workspace boilerplate from blueprint file."""
        spec = self.parse_blueprint(blueprint_file)
        schema = self.generate_db_schema(spec)
        forms = self.generate_crud_forms(spec)
        rbac = self.generate_rbac_stubs(spec)
        
        return {
            "spec": spec,
            "schema": schema,
            "crud_forms": forms,
            "rbac": rbac
        }
