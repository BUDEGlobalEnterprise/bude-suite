import ast
import re
from pathlib import Path


def test_flutter_bude_api_endpoint_references_resolve_to_backend_wrappers():
    repo = next(
        parent
        for parent in Path(__file__).resolve().parents
        if (parent / "mobile-app").is_dir() and (parent / "backend").is_dir()
    )
    api_dir = repo / "backend" / "bude_api" / "bude_api" / "api"
    mobile_dir = repo / "mobile-app"
    endpoint_pattern = re.compile(
        r"/api/method/bude_api\.api\.([A-Za-z0-9_]+)\.([A-Za-z0-9_]+)"
    )

    backend_functions = {}
    for path in api_dir.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        backend_functions[path.stem] = {
            node.name for node in tree.body if isinstance(node, ast.FunctionDef)
        }

    missing = []
    checked = 0
    for path in mobile_dir.rglob("*.dart"):
        if any(part in {".dart_tool", "build"} for part in path.parts):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for module, function in endpoint_pattern.findall(text):
            checked += 1
            if function not in backend_functions.get(module, set()):
                missing.append(f"{path.relative_to(repo)} -> {module}.{function}")

    assert checked > 0
    assert missing == []
