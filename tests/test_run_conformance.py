import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml

from scripts import run_conformance


class RunConformanceTests(unittest.TestCase):
    def _copy_fixture_inputs(self, root: Path) -> None:
        for relative_path in [
            "fixtures/discovery/api-catalog.linkset.json",
            "fixtures/discovery/service-meta.linkset.json",
            "fixtures/openapi/tickets.openapi.yaml",
            "fixtures/overlays/tickets.overlay.yaml",
            "fixtures/workflows/tickets.arazzo.yaml",
            "fixtures/skills/tickets.skill.json",
            "fixtures/config/project.cli.json",
        ]:
            destination = root / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text((run_conformance.ROOT / relative_path).read_text())

    def _write_fixture_validation_schemas(self, schema_root: Path) -> None:
        (schema_root / "skill-manifest.schema.json").write_text(json.dumps({
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "required": ["oasCliSkill", "serviceId", "toolGuidance"],
            "properties": {
                "oasCliSkill": {"type": "string"},
                "serviceId": {"type": "string"},
                "toolGuidance": {"type": "object"},
            },
        }))
        (schema_root / "cli.schema.json").write_text(json.dumps({
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "required": ["cli", "mode", "sources"],
            "properties": {
                "cli": {"type": "string"},
                "mode": {
                    "type": "object",
                    "required": ["default"],
                    "properties": {
                        "default": {"enum": ["discover", "curated"]},
                    },
                },
                "sources": {"type": "object"},
            },
        }))

    def test_resolve_schema_root_uses_explicit_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            schema_root = Path(temp_dir) / "schemas"
            schema_root.mkdir()

            resolved = run_conformance.resolve_schema_root(schema_root)

            self.assertEqual(schema_root, resolved)

    def test_resolve_schema_root_raises_clear_error_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            missing = Path(temp_dir) / "missing-schemas"
            fake_root = Path(temp_dir) / "repo-root"
            fake_root.mkdir()

            with mock.patch.object(run_conformance, "ROOT", fake_root):
                with self.assertRaisesRegex(FileNotFoundError, "schema root"):
                    run_conformance.resolve_schema_root(missing)

    def test_validate_compatibility_matrix_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "conformance"
            schema_root = Path(temp_dir) / "schemas"
            root.mkdir()
            schema_root.mkdir()

            (root / "README.md").write_text("See COMPATIBILITY.md for the published matrix.\n")
            (root / "COMPATIBILITY.md").write_text("# Compatibility\n")
            (root / "compatibility-matrix.json").write_text(json.dumps({
                "suiteVersion": "1.0.0",
                "specVersion": "0.1.0",
                "publishedAt": "2026-03-13T12:00:00Z",
                "implementations": [
                    {
                        "repo": "https://github.com/example/oas-cli-go",
                        "version": "main",
                        "status": "passing",
                        "features": {
                            "httpCaching": "passing",
                            "refresh": "passing",
                            "observabilityHooks": "passing",
                            "compatibilityMatrix": "passing"
                        }
                    }
                ]
            }))
            (schema_root / "compatibility-matrix.schema.json").write_text(json.dumps({
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "required": ["suiteVersion", "specVersion", "publishedAt", "implementations"]
            }))

            with mock.patch.object(run_conformance, "ROOT", root):
                run_conformance.validate_compatibility_matrix(schema_root)
                run_conformance.validate_docs_linkage()

    def test_validate_compatibility_matrix_fails_when_required_fields_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "conformance"
            schema_root = Path(temp_dir) / "schemas"
            root.mkdir()
            schema_root.mkdir()

            (root / "README.md").write_text("See COMPATIBILITY.md for the published matrix.\n")
            (root / "COMPATIBILITY.md").write_text("# Compatibility\n")
            (root / "compatibility-matrix.json").write_text(json.dumps({
                "suiteVersion": "1.0.0"
            }))
            (schema_root / "compatibility-matrix.schema.json").write_text(json.dumps({
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "required": ["suiteVersion", "specVersion", "publishedAt", "implementations"]
            }))

            with mock.patch.object(run_conformance, "ROOT", root):
                with self.assertRaises(SystemExit):
                    run_conformance.validate_compatibility_matrix(schema_root)

    def test_readme_mentions_compatibility_matrix(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "conformance"
            root.mkdir()
            (root / "README.md").write_text("Missing link\n")
            (root / "COMPATIBILITY.md").write_text("# Compatibility\n")

            with mock.patch.object(run_conformance, "ROOT", root):
                with self.assertRaises(SystemExit):
                    run_conformance.validate_docs_linkage()

    def test_main_fails_when_skill_manifest_fixture_violates_schema(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "conformance"
            schema_root = Path(temp_dir) / "schemas"
            root.mkdir()
            schema_root.mkdir()
            self._copy_fixture_inputs(root)
            self._write_fixture_validation_schemas(schema_root)

            skill_manifest_path = root / "fixtures" / "skills" / "tickets.skill.json"
            skill_manifest = json.loads(skill_manifest_path.read_text())
            skill_manifest.pop("toolGuidance")
            skill_manifest_path.write_text(json.dumps(skill_manifest))

            with (
                mock.patch.object(run_conformance, "ROOT", root),
                mock.patch.object(run_conformance, "resolve_schema_root", return_value=schema_root),
                mock.patch.object(run_conformance, "validate_expected_ntc"),
                mock.patch.object(run_conformance, "validate_compatibility_matrix"),
                mock.patch.object(run_conformance, "validate_docs_linkage"),
                mock.patch("sys.argv", ["run_conformance.py"]),
            ):
                with self.assertRaisesRegex(SystemExit, r"(?s)tickets\.skill\.json.*toolGuidance"):
                    run_conformance.main()

    def test_main_fails_when_cli_fixture_violates_schema(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "conformance"
            schema_root = Path(temp_dir) / "schemas"
            root.mkdir()
            schema_root.mkdir()
            self._copy_fixture_inputs(root)
            self._write_fixture_validation_schemas(schema_root)

            cli_config_path = root / "fixtures" / "config" / "project.cli.json"
            cli_config = json.loads(cli_config_path.read_text())
            cli_config["mode"]["default"] = "invalid"
            cli_config_path.write_text(json.dumps(cli_config))

            with (
                mock.patch.object(run_conformance, "ROOT", root),
                mock.patch.object(run_conformance, "resolve_schema_root", return_value=schema_root),
                mock.patch.object(run_conformance, "validate_expected_ntc"),
                mock.patch.object(run_conformance, "validate_compatibility_matrix"),
                mock.patch.object(run_conformance, "validate_docs_linkage"),
                mock.patch("sys.argv", ["run_conformance.py"]),
            ):
                with self.assertRaisesRegex(SystemExit, r"(?s)project\.cli\.json.*mode\.default.*invalid"):
                    run_conformance.main()

    def test_validate_fixture_shapes_fails_when_config_references_missing_skill_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "conformance"
            schema_root = Path(temp_dir) / "schemas"
            root.mkdir()
            schema_root.mkdir()
            self._copy_fixture_inputs(root)
            self._write_fixture_validation_schemas(schema_root)

            cli_config_path = root / "fixtures" / "config" / "project.cli.json"
            cli_config = json.loads(cli_config_path.read_text())
            cli_config["services"]["tickets"]["skills"] = ["../skills/DOES-NOT-EXIST.json"]
            cli_config_path.write_text(json.dumps(cli_config))

            with mock.patch.object(run_conformance, "ROOT", root):
                with self.assertRaisesRegex(SystemExit, r"DOES-NOT-EXIST\.json"):
                    run_conformance.validate_fixture_shapes(schema_root)

    def test_validate_fixture_shapes_fails_when_openapi_fixture_lacks_expected_request_body_schema(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "conformance"
            schema_root = Path(temp_dir) / "schemas"
            root.mkdir()
            schema_root.mkdir()
            self._copy_fixture_inputs(root)
            self._write_fixture_validation_schemas(schema_root)

            openapi_path = root / "fixtures" / "openapi" / "tickets.openapi.yaml"
            document = yaml.safe_load(openapi_path.read_text())
            del document["paths"]["/tickets"]["post"]["requestBody"]
            openapi_path.write_text(yaml.safe_dump(document, sort_keys=False))

            with mock.patch.object(run_conformance, "ROOT", root):
                with self.assertRaisesRegex(SystemExit, r"createTicket.*requestBody"):
                    run_conformance.validate_fixture_shapes(schema_root)

    def test_validate_fixture_shapes_fails_when_overlay_fixture_omits_expected_cli_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "conformance"
            schema_root = Path(temp_dir) / "schemas"
            root.mkdir()
            schema_root.mkdir()
            self._copy_fixture_inputs(root)
            self._write_fixture_validation_schemas(schema_root)

            overlay_path = root / "fixtures" / "overlays" / "tickets.overlay.yaml"
            document = yaml.safe_load(overlay_path.read_text())
            document["actions"][0]["update"].pop("x-cli-pagination")
            overlay_path.write_text(yaml.safe_dump(document, sort_keys=False))

            with mock.patch.object(run_conformance, "ROOT", root):
                with self.assertRaisesRegex(SystemExit, r"x-cli-pagination"):
                    run_conformance.validate_fixture_shapes(schema_root)


if __name__ == "__main__":
    unittest.main()
