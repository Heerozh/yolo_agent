# Repository Guidelines

## Project Structure & Module Organization

This is a small Python CLI package using a `src/` layout. The package lives in `src/yolo_agent/`; `cli.py` contains the launcher, Docker command construction, DinD sidecar handling, config mounts, and command shortcuts. Packaged runtime image assets live in `src/yolo_agent/runtime/` and are included in the wheel by `pyproject.toml`. Unit tests are in `tests/test_cli.py`. The top-level `docker/` directory contains auxiliary container assets, while `README.md` is the user-facing behavior reference.

## Build, Test, and Development Commands

- `py -m pip install -e .`: install the package locally and expose the `agent` console script.
- `uv run python -m unittest discover -s tests`: run the test suite.
- `agent --dry-run`: print the Docker commands the launcher would execute.
- `agent --no-run`: build the packaged runtime image without starting a container.
- `agent --no-build -- bash -lc "pwd && docker version"`: run a command inside the agent container while skipping the image build.

## Coding Style & Naming Conventions

Target Python 3.10 or newer. Follow the existing style: four-space indentation, `from __future__ import annotations`, typed function signatures, `Path` for filesystem paths, and pure helper functions. Use `snake_case` for functions and variables, `PascalCase` for dataclasses and test classes, and `UPPER_SNAKE_CASE` for constants. Keep CLI option names long-form and descriptive, matching the existing `--no-build`, `--docker-mode`, and `--dind-*` patterns.

## Testing Guidelines

Tests use Python `unittest`, with methods named `test_<behavior>`. Prefer focused tests around command construction, argument normalization, environment handling, and state-file behavior. Avoid requiring real Docker for unit tests; mock subprocess or environment access where possible. When changing `src/yolo_agent/runtime/`, update tests that verify packaged paths and entrypoint behavior.

## Commit & Pull Request Guidelines

The current Git history uses short, direct, feature-focused commit subjects without a strict prefix convention. Keep new commits concise and imperative, for example `add socket mode coverage` or `fix dind cleanup state`. Pull requests should describe the behavior change, list commands run, call out Docker/runtime implications, and link related issues when available.

## Security & Configuration Tips

Do not log secret values such as `GH_TOKEN`, `GITHUB_TOKEN`, or tokens read from `gh auth token`. Preserve existing user config files when editing Claude, Codex, Gemini, or Docker mount behavior, and prefer passing sensitive values by environment variable name rather than embedding values in command lines.
