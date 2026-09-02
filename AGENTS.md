# Repository Guidelines

## Project Structure & Module Organization

The Home Assistant custom integration lives in `custom_components/tplink_easy_smart/`. Home Assistant platforms (`sensor.py`, `switch.py`, `select.py`, and `binary_sensor.py`) should remain thin; shared polling belongs in `update_coordinator.py`, services in `services.py`, and TP-Link HTTP/parsing logic in `client/`. Keep user-facing text synchronized across `strings.json` and `translations/`. Tests are under `tests/`, user documentation under `docs/`, and CI/release automation under `.github/workflows/`.

## Build, Test, and Development Commands

Use Python 3.14 or newer and [`uv`](https://docs.astral.sh/uv/) from the repository root:

- `uv sync --group dev` installs locked runtime and development dependencies.
- `uv run pytest` runs the complete test suite.
- `uv run pytest tests/test_configuration_api.py -q` runs a focused test module.
- `uv run ruff check .` checks imports, correctness, and style.
- `uv run ruff format --check .` verifies formatting without modifying files.
- `uv lock --check` confirms that `uv.lock` matches `pyproject.toml`.

This HACS repository has no separate build step. Validate integration metadata and JSON files before release through the existing GitHub Actions workflow.

## Coding Style & Naming Conventions

Use four-space indentation, type annotations, asynchronous I/O, and an 88-character line limit. Ruff enforces `E`, `F`, `I`, `UP`, `B`, `SIM`, and `RUF` rules. Use `snake_case` for modules, functions, and variables; `PascalCase` for classes; and `UPPER_SNAKE_CASE` for constants. Preserve Home Assistant entity unique IDs and TP-Link CGI field names. Use capability checks for model- or firmware-specific behavior rather than assuming every switch supports every endpoint.

## Testing Guidelines

Tests use `pytest`, `pytest-asyncio`, and Home Assistant custom-component fixtures. Name files `test_<area>.py` and tests `test_<behavior>`. Add regression coverage for parser changes, config flows, services, and configuration writes. Mock switch traffic; never require a physical device or live credentials. There is no numeric coverage threshold, but each new behavior and bug fix should include focused tests.

## Commit & Pull Request Guidelines

History favors short, single-purpose subjects such as `Fixed config flow`, `Added auto-detection...`, and occasional `fix:` prefixes. Keep commits similarly concise and scoped. Pull requests should explain what changed and why, list tested switch models and firmware, include test/lint results, and link related issues. Add screenshots for visible Home Assistant UI changes. Never commit passwords, device addresses, captured session cookies, or unredacted network dumps.

Releases use Home Assistant-style calendar versions such as `2026.9.0`; update the manifest, project metadata, lockfile, and changelog together.
