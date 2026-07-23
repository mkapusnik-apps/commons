#!/usr/bin/env python3
"""Validate repository-specific contracts for reusable local actions."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover - exercised by CI setup failures only.
    print(
        "PyYAML is required. Install it with: python3 -m pip install PyYAML==6.0.3",
        file=sys.stderr,
    )
    sys.exit(2)


class ValidationError(Exception):
    """Raised when an action contract is incomplete."""


EXPECTED_CONTRACTS = {
    Path(".github/actions/git-ref/action.yml"): {
        "name": "Set Git Ref",
        "inputs": {
            "repository": {"required": False, "default": "${{ github.repository }}"},
            "ref": {"required": True},
            "commit_sha": {"required": False, "default": "${{ github.sha }}"},
            "token": {"required": True},
            "force": {"required": False, "default": "true"},
            "create_if_missing": {"required": False, "default": "true"},
            "noop_if_unchanged": {"required": False, "default": "true"},
        },
        "outputs": {"changed", "previous_sha", "new_sha", "ref"},
        "documentation": Path(".github/actions/git-ref/README.md"),
        "token_env": "GIT_REF_TOKEN",
        "token_error": 'Input "token" must be a non-empty string',
    },
    Path(".github/actions/workflow-state/action.yml"): {
        "name": "Set Workflow State",
        "inputs": {
            "workflow": {"required": True},
            "state": {"required": True},
            "repository": {"required": False, "default": "${{ github.repository }}"},
            "token": {"required": True},
        },
        "outputs": {"changed", "previous_state", "new_state", "workflow_id", "workflow_path"},
        "documentation": Path(".github/actions/workflow-state/README.md"),
        "token_env": "WORKFLOW_STATE_TOKEN",
        "token_error": 'Input "token" must be a non-empty string',
    },
    Path(".github/actions/tag-gate/action.yml"): {
        "name": "Lifecycle Tag Gate",
        "inputs": {
            "source_tag": {"required": True},
            "target_tag": {"required": True},
            "repository": {"required": False, "default": "${{ github.repository }}"},
            "remote": {"required": False, "default": "origin"},
        },
        "outputs": {"should_run", "source_sha", "target_sha", "short_sha", "reason"},
        "documentation": Path(".github/actions/tag-gate/README.md"),
        "required_script_snippets": [
            "git check-ref-format",
            "source-missing",
            "already-current",
            "pending",
        ],
    },
}


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValidationError(f"{path}: expected action metadata file to exist")

    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)

    if not isinstance(data, dict):
        raise ValidationError(f"{path}: action metadata must be a mapping")

    return data


def require_mapping(value: Any, path: Path, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValidationError(f"{path}: {field} must be a mapping")
    return value


def validate_inputs(path: Path, metadata: dict[str, Any], expected: dict[str, dict[str, Any]]) -> None:
    inputs = require_mapping(metadata.get("inputs"), path, "inputs")
    missing = set(expected) - set(inputs)
    extra = set(inputs) - set(expected)

    if missing:
        raise ValidationError(f"{path}: missing expected inputs: {', '.join(sorted(missing))}")
    if extra:
        raise ValidationError(f"{path}: unexpected inputs: {', '.join(sorted(extra))}")

    for input_name, expected_metadata in expected.items():
        input_metadata = require_mapping(inputs[input_name], path, f"inputs.{input_name}")
        expected_required = expected_metadata.get("required")
        if input_metadata.get("required") is not expected_required:
            raise ValidationError(f"{path}: inputs.{input_name}.required must be {expected_required!r}")

        if "default" in expected_metadata and str(input_metadata.get("default")) != expected_metadata["default"]:
            raise ValidationError(
                f"{path}: inputs.{input_name}.default must be {expected_metadata['default']!r}"
            )


def validate_outputs(path: Path, metadata: dict[str, Any], expected: set[str]) -> None:
    outputs = require_mapping(metadata.get("outputs"), path, "outputs")
    missing = expected - set(outputs)
    extra = set(outputs) - expected

    if missing:
        raise ValidationError(f"{path}: missing expected outputs: {', '.join(sorted(missing))}")
    if extra:
        raise ValidationError(f"{path}: unexpected outputs: {', '.join(sorted(extra))}")


def validate_documentation(path: Path) -> None:
    if not path.is_file():
        raise ValidationError(f"{path}: expected action README to exist")

    text = path.read_text(encoding="utf-8")
    required_snippets = ["## Inputs", "## Outputs", "## Permissions", "pin"]
    missing = [snippet for snippet in required_snippets if snippet not in text]
    if missing:
        raise ValidationError(f"{path}: missing documentation snippets: {', '.join(missing)}")


def validate_token_validation(path: Path, metadata: dict[str, Any], token_env: str, token_error: str) -> None:
    runs = require_mapping(metadata.get("runs"), path, "runs")
    steps = runs.get("steps")
    if not isinstance(steps, list) or not steps:
        raise ValidationError(f"{path}: runs.steps must be a non-empty list")

    first_step = require_mapping(steps[0], path, "runs.steps[1]")
    env = require_mapping(first_step.get("env"), path, "runs.steps[1].env")
    if env.get(token_env) != "${{ inputs.token }}":
        raise ValidationError(f"{path}: runs.steps[1].env.{token_env} must map to inputs.token")

    with_metadata = require_mapping(first_step.get("with"), path, "runs.steps[1].with")
    script = with_metadata.get("script")
    if not isinstance(script, str):
        raise ValidationError(f"{path}: runs.steps[1].with.script must be a string")
    if f"process.env.{token_env}" not in script:
        raise ValidationError(f"{path}: script must read {token_env} from the environment")
    if token_error not in script:
        raise ValidationError(f"{path}: script must explicitly fail on an empty token input")


def validate_action_script(path: Path, snippets: list[str]) -> None:
    script_path = path.with_name("tag-gate.sh")
    if not script_path.is_file():
        raise ValidationError(f"{script_path}: expected action shell script to exist")

    text = script_path.read_text(encoding="utf-8")
    missing = [snippet for snippet in snippets if snippet not in text]
    if missing:
        raise ValidationError(f"{script_path}: missing script snippets: {', '.join(missing)}")


def validate_contract(path: Path, contract: dict[str, Any]) -> None:
    metadata = load_yaml(path)
    if metadata.get("name") != contract["name"]:
        raise ValidationError(f"{path}: name must be {contract['name']!r}")

    validate_inputs(path, metadata, contract["inputs"])
    validate_outputs(path, metadata, contract["outputs"])
    validate_documentation(contract["documentation"])
    if "token_env" in contract:
        validate_token_validation(path, metadata, contract["token_env"], contract["token_error"])
    if "required_script_snippets" in contract:
        validate_action_script(path, contract["required_script_snippets"])


def main() -> int:
    errors: list[str] = []

    for path, contract in EXPECTED_CONTRACTS.items():
        try:
            validate_contract(path, contract)
            print(f"OK reusable action contract: {path}")
        except (OSError, yaml.YAMLError, ValidationError) as error:
            errors.append(str(error))

    if errors:
        print("\nContract validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print(f"Validated {len(EXPECTED_CONTRACTS)} reusable action contract(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
