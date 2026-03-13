#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
SPEC_ROOT = ROOT.parent / "oas-cli-spec"


def load_json(path: Path):
    return json.loads(path.read_text())


def validate_expected_ntc() -> None:
    schema = load_json(SPEC_ROOT / "schemas" / "ntc.schema.json")
    expected = load_json(ROOT / "expected" / "tickets.ntc.json")
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(expected), key=lambda error: list(error.path))
    if errors:
        raise SystemExit("\n".join(
            ["expected/tickets.ntc.json failed schema validation:"]
            + [f"  - {'.'.join(str(part) for part in error.path) or '<root>'}: {error.message}" for error in errors]
        ))


def validate_fixture_shapes() -> None:
    load_json(ROOT / "fixtures" / "discovery" / "api-catalog.linkset.json")
    load_json(ROOT / "fixtures" / "discovery" / "service-meta.linkset.json")
    yaml.safe_load((ROOT / "fixtures" / "openapi" / "tickets.openapi.yaml").read_text())
    yaml.safe_load((ROOT / "fixtures" / "overlays" / "tickets.overlay.yaml").read_text())
    yaml.safe_load((ROOT / "fixtures" / "workflows" / "tickets.arazzo.yaml").read_text())
    load_json(ROOT / "fixtures" / "config" / "project.cli.json")


def compare_candidate(candidate_path: Path) -> None:
    candidate = normalize_ntc(load_json(candidate_path))
    expected = normalize_ntc(load_json(ROOT / "expected" / "tickets.ntc.json"))
    if candidate != expected:
        raise SystemExit(f"candidate output {candidate_path} does not match expected/tickets.ntc.json")


def normalize_ntc(document: dict) -> dict:
    normalized = json.loads(json.dumps(document))
    normalized.pop("generatedAt", None)
    normalized.pop("sourceFingerprint", None)
    return normalized


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", type=Path)
    args = parser.parse_args()

    validate_fixture_shapes()
    validate_expected_ntc()
    if args.candidate:
        compare_candidate(args.candidate)
    print("conformance fixture validation passed")


if __name__ == "__main__":
    main()
