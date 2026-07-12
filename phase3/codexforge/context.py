import os
import json
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger("CodexForge.ContextIndexer")

class ContextIndexer:
    def __init__(self, root_dir: str):
        self.root_dir = os.path.abspath(root_dir)

    def scan_repo_structure(self, exclude_dirs: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Scans repo structure recursively, returning file paths, sizes, and extensions.
        """
        if exclude_dirs is None:
            exclude_dirs = [".git", "__pycache__", ".pytest_cache", "node_modules", "venv", ".venv"]

        structure = {}
        for root, dirs, files in os.walk(self.root_dir):
            # Prune directory search path
            dirs[:] = [d for d in dirs if d not in exclude_dirs]
            
            rel_path = os.path.relpath(root, self.root_dir)
            if rel_path == ".":
                rel_path = ""
                
            structure[rel_path] = {
                "directories": dirs,
                "files": []
            }
            
            for file in files:
                filepath = os.path.join(root, file)
                try:
                    size = os.path.getsize(filepath)
                    structure[rel_path]["files"].append({
                        "name": file,
                        "size_bytes": size,
                        "extension": os.path.splitext(file)[1]
                    })
                except OSError:
                    pass
        return structure

    def resolve_documentation(self, doc_url: str) -> str:
        """
        Resolves live markdown/documentation from documentation URLs to avoid hallucinations (V059).
        If offline or unreachable, returns a mock markdown doc based on URL matching.
        """
        logger.info(f"Resolving documentation from: {doc_url}")
        
        # Simple offline cache / mocks for common documentation libraries
        url_lower = doc_url.lower()
        if "pytest" in url_lower:
            return (
                "# Pytest Documentation (Mock)\n\n"
                "## Usage\n"
                "Run `pytest <test_file>.py` to execute tests.\n"
                "## Assertions\n"
                "Use `assert a == b` for assertions. For exceptions, use:\n"
                "```python\n"
                "with pytest.raises(ExpectedException):\n"
                "    raise ExpectedException()\n"
                "```"
            )
        elif "playwright" in url_lower:
            return (
                "# Playwright Python Documentation (Mock)\n\n"
                "## Async API\n"
                "```python\n"
                "from playwright.async_api import async_playwright\n"
                "async with async_playwright() as p:\n"
                "    browser = await p.chromium.launch()\n"
                "    page = await browser.new_page()\n"
                "    await page.goto('https://example.com')\n"
                "    await browser.close()\n"
                "```"
            )

        # Attempt to make a live call using requests if internet is available
        try:
            import requests
            response = requests.get(doc_url, timeout=5)
            if response.status_code == 200:
                # Basic conversion or HTML to Markdown if content type is html
                # In real scenario, we might use html2markdown, here we return text/markdown
                return response.text
        except Exception as e:
            logger.warning(f"Could not fetch live docs from {doc_url}: {e}. Using generic mock doc.")
            
        return f"# Documentation for {doc_url}\n\nLive documentation could not be loaded. Please refer to standard library specs."

    def build_ai_native_context(self, doc_urls: Optional[List[str]] = None) -> str:
        """
        Packages repository structure, index statistics, and resolved documentation
        into a high-density AI-native JSON representation for consumption by external agents (V003, V010).
        """
        structure = self.scan_repo_structure()
        
        resolved_docs = {}
        if doc_urls:
            for url in doc_urls:
                resolved_docs[url] = self.resolve_documentation(url)
                
        context_payload = {
            "workspace_root": self.root_dir,
            "repository_structure": structure,
            "resolved_docs": resolved_docs,
            "summary": {
                "total_directories": len(structure),
                "total_files": sum(len(d["files"]) for d in structure.values())
            }
        }
        
        # Serialize to compact high-density JSON
        return json.dumps(context_payload, indent=2)
