import json
from pathlib import Path


def _read_template(path: Path) -> dict | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return None
        return payload
    except (OSError, json.JSONDecodeError):
        return None


def list_templates(templates_dir: Path) -> list[dict]:
    if not templates_dir.exists():
        return []

    templates: list[dict] = []
    for path in sorted(templates_dir.glob("*.json")):
        payload = _read_template(path)
        if payload is None:
            continue

        try:
            templates.append(
                {
                    "template_id": str(payload.get("template_id", path.stem)),
                    "version": int(payload.get("version", 1)),
                    "title": str(payload.get("title", path.stem)),
                    "required_fields": payload.get("required_fields", []),
                }
            )
        except (ValueError, TypeError):
            continue

    return templates


def get_template(templates_dir: Path, template_id: str) -> dict | None:
    if not templates_dir.exists():
        return None

    for path in sorted(templates_dir.glob("*.json")):
        payload = _read_template(path)
        if payload is None:
            continue

        if str(payload.get("template_id", path.stem)) == template_id:
            return payload

    return None
