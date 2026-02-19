import hashlib
import json
from pathlib import Path


def build_tree(root: Path, max_depth: int = 4) -> dict:
    root = root.resolve()

    def walk(path: Path, depth: int) -> dict:
        node = {
            "name": path.name if path != root else root.name,
            "path": str(path),
            "is_dir": path.is_dir(),
            "children": [],
        }

        if not path.is_dir() or depth >= max_depth:
            return node

        try:
            children = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except OSError:
            return node

        for child in children:
            if child.name.startswith("."):
                continue
            node["children"].append(walk(child, depth + 1))

        return node

    return walk(root, 0)


def top_level_folders(tree: dict) -> list[str]:
    children = tree.get("children", [])
    if not isinstance(children, list):
        return []

    names: list[str] = []
    for child in children:
        if child.get("is_dir"):
            names.append(str(child.get("name", "")))

    return names


def tree_signature(tree: dict) -> str:
    serialized = json.dumps(tree, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
