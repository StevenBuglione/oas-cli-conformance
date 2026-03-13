#!/usr/bin/env python3
import argparse
import json
import os
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]


def load_json(path: Path):
    return json.loads(path.read_text())


def fail_validation(message: str) -> None:
    raise SystemExit(message)


def resolve_schema_root(explicit_root: Path | None = None) -> Path:
    candidates = []
    if explicit_root is not None:
        candidates.append(explicit_root)

    env_root = os.getenv("OASCLI_SCHEMA_ROOT")
    if env_root:
        candidates.append(Path(env_root))

    candidates.append(ROOT.parent / "oas-cli-spec" / "schemas")

    for candidate in candidates:
        if candidate.exists() and candidate.is_dir():
            return candidate

    searched = ", ".join(str(candidate) for candidate in candidates)
    raise FileNotFoundError(f"schema root not found; searched: {searched}")


def validate_expected_ntc(schema_root: Path) -> None:
    schema = load_json(schema_root / "ntc.schema.json")
    expected = load_json(ROOT / "expected" / "tickets.ntc.json")
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(expected), key=lambda error: list(error.path))
    if errors:
        raise SystemExit("\n".join(
            ["expected/tickets.ntc.json failed schema validation:"]
            + [f"  - {'.'.join(str(part) for part in error.path) or '<root>'}: {error.message}" for error in errors]
        ))


def validate_compatibility_matrix(schema_root: Path) -> None:
    schema = load_json(schema_root / "compatibility-matrix.schema.json")
    matrix = load_json(ROOT / "compatibility-matrix.json")
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(matrix), key=lambda error: list(error.path))
    if errors:
        raise SystemExit("\n".join(
            ["compatibility-matrix.json failed schema validation:"]
            + [f"  - {'.'.join(str(part) for part in error.path) or '<root>'}: {error.message}" for error in errors]
        ))


def validate_json_fixture(path: Path, schema_root: Path, schema_name: str) -> None:
    if not path.exists():
        fail_validation(f"{path.relative_to(ROOT)} is missing")
    schema = load_json(schema_root / schema_name)
    document = load_json(path)
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(document), key=lambda error: list(error.path))
    if errors:
        fail_validation("\n".join(
            [f"{path.relative_to(ROOT)} failed schema validation:"]
            + [f"  - {'.'.join(str(part) for part in error.path) or '<root>'}: {error.message}" for error in errors]
        ))


def load_yaml_fixture(path: Path) -> dict:
    if not path.exists():
        fail_validation(f"{path.relative_to(ROOT)} is missing")
    document = yaml.safe_load(path.read_text())
    if not isinstance(document, dict):
        fail_validation(f"{path.relative_to(ROOT)} must contain a mapping document")
    return document


def resolve_config_reference(config_path: Path, relative_path: str) -> Path:
    return (config_path.parent / relative_path).resolve()


def require(condition: bool, message: str) -> None:
    if not condition:
        fail_validation(message)


def validate_openapi_fixture(path: Path) -> None:
    document = load_yaml_fixture(path)
    paths = document.get("paths")
    require(isinstance(paths, dict), f"{path.relative_to(ROOT)} must define OpenAPI paths")

    list_op = paths.get("/tickets", {}).get("get", {})
    require(list_op.get("operationId") == "listTickets", f"{path.relative_to(ROOT)} must define /tickets GET as operationId listTickets")

    create_op = paths.get("/tickets", {}).get("post", {})
    require(create_op.get("operationId") == "createTicket", f"{path.relative_to(ROOT)} must define /tickets POST as operationId createTicket")
    request_body = create_op.get("requestBody")
    require(isinstance(request_body, dict), f"{path.relative_to(ROOT)} createTicket must define requestBody")
    require(request_body.get("required") is True, f"{path.relative_to(ROOT)} createTicket requestBody must be required")
    content = request_body.get("content", {})
    json_body = content.get("application/json", {})
    require(isinstance(json_body.get("schema"), dict), f"{path.relative_to(ROOT)} createTicket requestBody must include an application/json schema")

    archive_op = paths.get("/tickets/archive", {}).get("post", {})
    require(archive_op.get("operationId") == "archiveTickets", f"{path.relative_to(ROOT)} must define /tickets/archive POST as operationId archiveTickets")

    purge_op = paths.get("/admin/tickets", {}).get("delete", {})
    require(purge_op.get("operationId") == "purgeTickets", f"{path.relative_to(ROOT)} must define /admin/tickets DELETE as operationId purgeTickets")


def _find_overlay_action(actions: list[dict], target: str) -> dict | None:
    for action in actions:
        if action.get("target") == target:
            return action
    return None


def validate_overlay_fixture(path: Path) -> None:
    document = load_yaml_fixture(path)
    actions = document.get("actions")
    require(isinstance(actions, list) and actions, f"{path.relative_to(ROOT)} must define overlay actions")

    list_action = _find_overlay_action(actions, "$.paths['/tickets'].get")
    require(isinstance(list_action, dict), f"{path.relative_to(ROOT)} must include an action for $.paths['/tickets'].get")
    list_update = list_action.get("update", {})
    require(list_update.get("x-cli-name") == "list", f"{path.relative_to(ROOT)} must set x-cli-name=list for $.paths['/tickets'].get")
    require(isinstance(list_update.get("x-cli-pagination"), dict), f"{path.relative_to(ROOT)} must define x-cli-pagination for $.paths['/tickets'].get")
    require(isinstance(list_update.get("x-cli-retry"), dict), f"{path.relative_to(ROOT)} must define x-cli-retry for $.paths['/tickets'].get")

    create_action = _find_overlay_action(actions, "$.paths['/tickets'].post")
    require(isinstance(create_action, dict), f"{path.relative_to(ROOT)} must include an action for $.paths['/tickets'].post")
    create_update = create_action.get("update", {})
    require(isinstance(create_update.get("x-cli-aliases"), list), f"{path.relative_to(ROOT)} must define x-cli-aliases for $.paths['/tickets'].post")
    require(isinstance(create_update.get("x-cli-output"), dict), f"{path.relative_to(ROOT)} must define x-cli-output for $.paths['/tickets'].post")

    archive_action = _find_overlay_action(actions, "$.paths['/tickets/archive'].post")
    require(isinstance(archive_action, dict), f"{path.relative_to(ROOT)} must include an action for $.paths['/tickets/archive'].post")
    require(archive_action.get("update", {}).get("x-cli-hidden") is True, f"{path.relative_to(ROOT)} must mark $.paths['/tickets/archive'].post as x-cli-hidden")

    purge_action = _find_overlay_action(actions, "$.paths['/admin/tickets'].delete")
    require(isinstance(purge_action, dict), f"{path.relative_to(ROOT)} must include an action for $.paths['/admin/tickets'].delete")
    require(purge_action.get("update", {}).get("x-cli-ignore") is True, f"{path.relative_to(ROOT)} must mark $.paths['/admin/tickets'].delete as x-cli-ignore")


def validate_workflow_fixture(path: Path) -> None:
    document = load_yaml_fixture(path)
    workflows = document.get("workflows")
    require(isinstance(workflows, list) and workflows, f"{path.relative_to(ROOT)} must define workflows")
    workflow = workflows[0]
    require(workflow.get("workflowId") == "triageTicket", f"{path.relative_to(ROOT)} must define workflowId triageTicket")
    steps = workflow.get("steps")
    require(isinstance(steps, list) and len(steps) >= 2, f"{path.relative_to(ROOT)} triageTicket must define at least two steps")
    require(steps[0].get("operationId") == "listTickets", f"{path.relative_to(ROOT)} triageTicket first step must reference listTickets")
    require(steps[1].get("operationId") == "getTicket", f"{path.relative_to(ROOT)} triageTicket second step must reference getTicket")


def validate_fixture_shapes(schema_root: Path) -> None:
    load_json(ROOT / "fixtures" / "discovery" / "api-catalog.linkset.json")
    load_json(ROOT / "fixtures" / "discovery" / "service-meta.linkset.json")
    config_path = ROOT / "fixtures" / "config" / "project.cli.json"
    validate_json_fixture(config_path, schema_root, "cli.schema.json")
    config = load_json(config_path)

    sources = config.get("sources", {})
    for source_name, source in sources.items():
        require(isinstance(source, dict), f"fixtures/config/project.cli.json source {source_name!r} must be an object")
        source_path = resolve_config_reference(config_path, source["uri"])
        if source.get("type") == "openapi":
            validate_openapi_fixture(source_path)
        elif source_path.suffix == ".json":
            load_json(source_path)
        else:
            load_yaml_fixture(source_path)

    for service_name, service in config.get("services", {}).items():
        require(isinstance(service, dict), f"fixtures/config/project.cli.json service {service_name!r} must be an object")
        source_name = service.get("source")
        require(source_name in sources, f"fixtures/config/project.cli.json service {service_name!r} references unknown source {source_name!r}")

        for relative_path in service.get("skills", []):
            validate_json_fixture(resolve_config_reference(config_path, relative_path), schema_root, "skill-manifest.schema.json")
        for relative_path in service.get("overlays", []):
            validate_overlay_fixture(resolve_config_reference(config_path, relative_path))
        for relative_path in service.get("workflows", []):
            validate_workflow_fixture(resolve_config_reference(config_path, relative_path))


def validate_docs_linkage() -> None:
    readme = (ROOT / "README.md").read_text()
    compatibility_doc = ROOT / "COMPATIBILITY.md"
    if not compatibility_doc.exists():
        raise SystemExit("COMPATIBILITY.md is missing")
    if "COMPATIBILITY.md" not in readme and "compatibility-matrix.json" not in readme:
        raise SystemExit("README.md must mention the published compatibility matrix")


def compare_candidate(candidate_path: Path) -> None:
    candidate = normalize_ntc(load_json(candidate_path))
    expected = normalize_ntc(load_json(ROOT / "expected" / "tickets.ntc.json"))
    if candidate != expected:
        raise SystemExit(f"candidate output {candidate_path} does not match expected/tickets.ntc.json")


def normalize_ntc(document: dict) -> dict:
    normalized = json.loads(json.dumps(document))
    normalized.pop("generatedAt", None)
    normalized.pop("sourceFingerprint", None)
    for source in normalized.get("sources", []):
        provenance = source.get("provenance", {})
        provenance.pop("at", None)
    return normalized


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--schema-root", type=Path)
    args = parser.parse_args()

    schema_root = resolve_schema_root(args.schema_root)
    validate_fixture_shapes(schema_root)
    validate_expected_ntc(schema_root)
    validate_compatibility_matrix(schema_root)
    validate_docs_linkage()
    if args.candidate:
        compare_candidate(args.candidate)
    print("conformance fixture validation passed")


if __name__ == "__main__":
    main()
