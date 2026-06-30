from __future__ import annotations

import json
from importlib import resources
from pathlib import Path
from typing import Any

from .ledger.jsonl import write_json


ARTIFACT_SCHEMA_VERSION = "artifact-schema-validation-v1"
SCHEMA_FILES = {
    "llm-review-packet": "llm_review_packet.schema.json",
    "external-review-response": "external_review_response.schema.json",
    "acquisition-manifest": "acquisition_manifest.schema.json",
}


class ArtifactSchemaError(ValueError):
    """Raised when artifact schema validation cannot be completed."""


def available_schemas() -> tuple[str, ...]:
    return tuple(sorted(SCHEMA_FILES))


def _schema_resource(schema_name: str):
    filename = SCHEMA_FILES.get(schema_name)
    if not filename:
        raise ArtifactSchemaError(f"Unknown schema '{schema_name}'. Available schemas: {', '.join(available_schemas())}")
    return resources.files("source_manifest_kit").joinpath("schemas", filename)


def load_schema(schema_name: str) -> dict[str, Any]:
    resource = _schema_resource(schema_name)
    try:
        with resource.open("r", encoding="utf-8") as handle:
            schema = json.load(handle)
    except FileNotFoundError as exc:
        raise ArtifactSchemaError(f"Packaged schema file is missing for '{schema_name}'.") from exc
    if not isinstance(schema, dict):
        raise ArtifactSchemaError(f"Schema '{schema_name}' must be a JSON object.")
    return schema


def validate_artifact_file(*, schema_name: str, artifact_file: str | Path) -> dict[str, Any]:
    try:
        from jsonschema import Draft202012Validator
    except ModuleNotFoundError as exc:
        raise ArtifactSchemaError(
            "jsonschema is required for validate-artifact. Install the optional schema extra, "
            "for example: pip install 'source-manifest-trust-kit[schema]'."
        ) from exc

    artifact_path = Path(artifact_file)
    try:
        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ArtifactSchemaError(f"Artifact file is not valid JSON: {artifact_path}") from exc

    schema = load_schema(schema_name)
    validator = Draft202012Validator(schema)
    errors = []
    for error in sorted(validator.iter_errors(artifact), key=lambda item: list(item.path)):
        location = "/" + "/".join(str(part) for part in error.path) if error.path else "/"
        errors.append({"path": location, "message": error.message})

    return {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "schema_name": schema_name,
        "artifact_file": str(artifact_path),
        "valid": not errors,
        "errors": errors,
    }


def write_artifact_validation(*, schema_name: str, artifact_file: str | Path, output_path: str | Path) -> Path:
    result = validate_artifact_file(schema_name=schema_name, artifact_file=artifact_file)
    output = Path(output_path)
    write_json(output, result)
    return output
