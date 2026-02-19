from app.schemas.patient import PatientSubmission


def _is_missing(value: object) -> bool:
    return value in (None, "", [])


def validate_submission_against_template(payload: PatientSubmission, template: dict) -> list[str]:
    errors: list[str] = []
    data = payload.model_dump(mode="json")

    required_fields = template.get("required_fields", [])
    for field_name in required_fields:
        value = data.get(field_name)
        if _is_missing(value):
            errors.append(f"Missing required field: {field_name}")

    field_defs = {
        field.get("key"): field
        for field in template.get("fields", [])
        if isinstance(field, dict) and field.get("key")
    }

    for key, value in data.items():
        field_def = field_defs.get(key)
        if not field_def:
            continue
        if _is_missing(value):
            continue

        field_type = field_def.get("type")
        if field_type == "enum":
            options = field_def.get("options", [])
            if value not in options:
                errors.append(f"Invalid enum value for {key}: {value}")

        if field_type == "date" and not isinstance(value, str):
            errors.append(f"Invalid date value for {key}")

        if field_type == "enum_list":
            options = field_def.get("options", [])
            if not isinstance(value, list):
                errors.append(f"Invalid list value for {key}")
            else:
                invalid_values = [item for item in value if item not in options]
                if invalid_values:
                    errors.append(f"Invalid enum list values for {key}: {', '.join(invalid_values)}")

    for key, field_def in field_defs.items():
        conditions = field_def.get("required_when")
        if not isinstance(conditions, dict) or not conditions:
            continue

        should_require = True
        for condition_key, condition_value in conditions.items():
            if data.get(condition_key) != condition_value:
                should_require = False
                break

        if should_require and _is_missing(data.get(key)):
            errors.append(f"Missing required field: {key} (conditional)")

    return errors
