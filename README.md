# oas-cli-conformance

Language-neutral fixtures and expected outputs for validating OAS-CLI implementations.

## Contents

- `fixtures/`: discovery, OpenAPI, overlay, workflow, and config inputs
- `expected/`: expected normalized outputs
- `scripts/run_conformance.py`: fixture validation and optional output comparison

## Usage

```bash
python3 -m pip install -r requirements.txt
python3 scripts/run_conformance.py
python3 scripts/run_conformance.py --candidate /path/to/generated.ntc.json
```
