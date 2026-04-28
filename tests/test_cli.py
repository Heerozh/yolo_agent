from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from typing import Any
from unittest.mock import patch

from yolo_agent.cli import (
    DEFAULT_UV_CACHE_DIR,
    DEFAULT_UV_DATA_ROOT,
    DEFAULT_UV_DATA_VOLUME,
    RunConfig,
    claude_settings_path,
    daily_cache_bust_value,
    default_workspace_path,
    default_runtime_build_paths,
    default_uv_project_environment,
    ensure_claude_bypass_permissions,
    existing_config_mounts,
    load_sidecar_records,
    make_build_command,
    make_build_args,
    make_run_command,
    make_sidecar_dind_command,
    normalize_remainder,
    parse_duration_seconds,
    project_slug,
    record_sidecar_use,
    resolve_container_command,
    resolve_build_enabled,
    resolve_dind_reuse,
    save_sidecar_records,
    should_cleanup_dind_after_run,
    stale_sidecar_records,
    with_sidecar_names,
)


class CliCommandTests(unittest.TestCase):
    def test_dind_mode_uses_sidecar_socket_and_network(self) -> None:
        config = RunConfig(
            docker_bin="docker",
            image="yolo-agent:latest",
            workspace="/workspace",
            host_cwd=Path("C:/project").resolve(),
            docker_mode="dind",
            dind_name="agent-dind-test",
            dind_run_volume="agent-dind-run-test",
            config_mounts=False,
            command=["bash"],
        )

        with patch.object(sys.stdin, "isatty", return_value=True), patch.object(
            sys.stdout, "isatty", return_value=True
        ):
            command = make_run_command(config)

        self.assertNotIn("--privileged", command)
        self.assertIn("--tty", command)
        self.assertIn("--interactive", command)
        self.assertIn("AGENT_DOCKER_MODE=dind", command)
        self.assertIn("DOCKER_HOST=unix:///var/run/docker.sock", command)
        self.assertIn("agent-dind-run-test:/var/run", command)
        self.assertIn("container:agent-dind-test", command)
        self.assertIn("yolo-agent.role=agent", command)
        self.assertIn("yolo-agent.sidecar=agent-dind-test", command)
        self.assertIn("bash", command)

        mount_index = command.index("--mount")
        self.assertEqual(
            command[mount_index + 1],
            f"type=bind,source={Path('C:/project').resolve()},target=/workspace",
        )

    def test_sidecar_dind_command_starts_privileged_daemon(self) -> None:
        config = RunConfig(
            docker_bin="docker",
            image="yolo-agent:latest",
            workspace="/workspace",
            host_cwd=Path("C:/project").resolve(),
            docker_mode="dind",
            dind_image="docker:dind",
            dind_name="agent-dind-test",
            dind_run_volume="agent-dind-run-test",
            ports=["8080:8080"],
        )

        command = make_sidecar_dind_command(config)

        self.assertIn("--privileged", command)
        self.assertIn("agent-dind-test", command)
        self.assertIn("agent-dind-run-test:/var/run", command)
        self.assertIn("8080:8080", command)
        self.assertIn("docker:dind", command)
        self.assertIn("--host=unix:///var/run/docker.sock", command)
        self.assertNotIn("--rm", command)
        self.assertIn("yolo-agent.role=dind", command)
        self.assertIn("yolo-agent.run-volume=agent-dind-run-test", command)

    def test_non_reused_sidecar_dind_is_removed_after_run(self) -> None:
        config = RunConfig(
            docker_bin="docker",
            image="yolo-agent:latest",
            workspace="/workspace",
            host_cwd=Path("C:/project").resolve(),
            docker_mode="dind",
            dind_image="docker:dind",
            dind_name="agent-dind-test",
            dind_run_volume="agent-dind-run-test",
            dind_reuse=False,
        )

        command = make_sidecar_dind_command(config)

        self.assertIn("--rm", command)
        self.assertTrue(should_cleanup_dind_after_run(config))

    def test_reused_sidecar_names_are_stable_for_workspace(self) -> None:
        config = RunConfig(
            docker_bin="docker",
            image="yolo-agent:latest",
            workspace="/workspace",
            host_cwd=Path("C:/project").resolve(),
            docker_mode="dind",
        )

        first = with_sidecar_names(config)
        second = with_sidecar_names(config)

        self.assertEqual(first.dind_name, second.dind_name)
        self.assertEqual(first.dind_run_volume, second.dind_run_volume)
        self.assertTrue(first.dind_name.startswith("agent-dind-project-"))
        self.assertTrue(first.dind_run_volume.startswith("agent-dind-run-project-"))

    def test_default_workspace_path_uses_current_directory_name(self) -> None:
        self.assertEqual(default_workspace_path(Path("C:/xsoft/hetu")), "/workspace-hetu")

    def test_project_slug_is_safe_for_container_path(self) -> None:
        self.assertEqual(project_slug("My Project!"), "My-Project")

    def test_sidecar_name_changes_when_container_workspace_changes(self) -> None:
        base = RunConfig(
            docker_bin="docker",
            image="yolo-agent:latest",
            workspace="/workspace-project",
            host_cwd=Path("C:/project").resolve(),
            docker_mode="dind",
        )
        other = RunConfig(
            docker_bin="docker",
            image="yolo-agent:latest",
            workspace="/workspace-other",
            host_cwd=Path("C:/project").resolve(),
            docker_mode="dind",
        )

        self.assertNotEqual(with_sidecar_names(base).dind_name, with_sidecar_names(other).dind_name)

    def test_inline_dind_mode_adds_privileged_to_agent_container(self) -> None:
        config = RunConfig(
            docker_bin="docker",
            image="yolo-agent:latest",
            workspace="/workspace",
            host_cwd=Path("C:/project").resolve(),
            docker_mode="inline-dind",
            dind_volume="agent-dind-data",
        )

        command = make_run_command(config)

        self.assertIn("--privileged", command)
        self.assertIn("agent-dind-data:/var/lib/docker", command)
        self.assertIn("AGENT_DOCKER_MODE=dind", command)

    def test_socket_mode_mounts_host_docker_socket(self) -> None:
        config = RunConfig(
            docker_bin="docker",
            image="yolo-agent:latest",
            workspace="/workspace",
            host_cwd=Path("C:/project").resolve(),
            docker_mode="socket",
        )

        command = make_run_command(config)

        self.assertNotIn("--privileged", command)
        self.assertIn(
            "type=bind,source=/var/run/docker.sock,target=/var/run/docker.sock",
            command,
        )
        self.assertIn("AGENT_DOCKER_MODE=socket", command)

    def test_clear_entrypoint_is_added_before_image(self) -> None:
        config = RunConfig(
            docker_bin="docker",
            image="yolo-agent:latest",
            workspace="/workspace",
            host_cwd=Path("C:/project").resolve(),
            docker_mode="none",
            config_mounts=False,
            clear_entrypoint=True,
            command=["bash", "-lc", "echo ok"],
        )

        command = make_run_command(config)

        self.assertLess(command.index("--entrypoint="), command.index("yolo-agent:latest"))

    def test_existing_config_mounts_include_known_agent_configs(self) -> None:
        config_home = Path("C:/tmp/yolo-agent-config-mounts-test")
        paths = [
            config_home / ".codex",
            config_home / ".gemini",
            config_home / ".claude_docker",
        ]
        file_path = config_home / ".claude_docker.json"
        for path in paths:
            path.mkdir(parents=True, exist_ok=True)
        file_path.write_text("{}", encoding="utf-8")

        try:
            self.assertEqual(
                existing_config_mounts(config_home),
                [
                    (config_home / ".codex", "/home/agent/.codex"),
                    (config_home / ".gemini", "/home/agent/.gemini"),
                    (config_home / ".claude_docker", "/home/agent/.claude"),
                    (config_home / ".claude_docker.json", "/home/agent/.claude.json"),
                ],
            )
        finally:
            file_path.unlink(missing_ok=True)
            for path in reversed(paths):
                path.rmdir()
            config_home.rmdir()

    def test_config_mounts_are_added_to_agent_container(self) -> None:
        config_home = Path("C:/tmp/yolo-agent-config-run-test")
        codex_path = config_home / ".codex"
        codex_path.mkdir(parents=True, exist_ok=True)
        config = RunConfig(
            docker_bin="docker",
            image="yolo-agent:latest",
            workspace="/workspace",
            host_cwd=Path("C:/project").resolve(),
            docker_mode="none",
            config_home=config_home,
        )

        try:
            command = make_run_command(config)

            self.assertIn(f"type=bind,source={codex_path},target=/home/agent/.codex", command)
        finally:
            codex_path.rmdir()
            config_home.rmdir()

    def test_uv_defaults_are_added_to_agent_container(self) -> None:
        config = RunConfig(
            docker_bin="docker",
            image="yolo-agent:latest",
            workspace="/workspace",
            host_cwd=Path("C:/project").resolve(),
            docker_mode="none",
            config_mounts=False,
        )

        command = make_run_command(config)

        self.assertIn(f"UV_PROJECT_ENVIRONMENT={default_uv_project_environment(config)}", command)
        self.assertIn(f"UV_CACHE_DIR={DEFAULT_UV_CACHE_DIR}", command)
        self.assertIn(f"AGENT_UV_DATA_ROOT={DEFAULT_UV_DATA_ROOT}", command)
        self.assertIn(f"{DEFAULT_UV_DATA_VOLUME}:{DEFAULT_UV_DATA_ROOT}", command)

    def test_user_uv_env_overrides_skip_matching_defaults(self) -> None:
        config = RunConfig(
            docker_bin="docker",
            image="yolo-agent:latest",
            workspace="/workspace",
            host_cwd=Path("C:/project").resolve(),
            docker_mode="none",
            config_mounts=False,
            env=["UV_PROJECT_ENVIRONMENT=/custom/env", "UV_CACHE_DIR=/custom/cache"],
        )

        command = make_run_command(config)

        self.assertIn("UV_PROJECT_ENVIRONMENT=/custom/env", command)
        self.assertIn("UV_CACHE_DIR=/custom/cache", command)
        self.assertNotIn(f"UV_PROJECT_ENVIRONMENT={default_uv_project_environment(config)}", command)
        self.assertNotIn(f"UV_CACHE_DIR={DEFAULT_UV_CACHE_DIR}", command)
        self.assertNotIn(f"AGENT_UV_DATA_ROOT={DEFAULT_UV_DATA_ROOT}", command)
        self.assertNotIn(f"{DEFAULT_UV_DATA_VOLUME}:{DEFAULT_UV_DATA_ROOT}", command)

    def test_uv_defaults_can_be_disabled(self) -> None:
        config = RunConfig(
            docker_bin="docker",
            image="yolo-agent:latest",
            workspace="/workspace",
            host_cwd=Path("C:/project").resolve(),
            docker_mode="none",
            config_mounts=False,
            uv_defaults=False,
        )

        command = make_run_command(config)

        self.assertNotIn(f"UV_PROJECT_ENVIRONMENT={default_uv_project_environment(config)}", command)
        self.assertNotIn(f"UV_CACHE_DIR={DEFAULT_UV_CACHE_DIR}", command)
        self.assertNotIn(f"AGENT_UV_DATA_ROOT={DEFAULT_UV_DATA_ROOT}", command)
        self.assertNotIn(f"{DEFAULT_UV_DATA_VOLUME}:{DEFAULT_UV_DATA_ROOT}", command)

    def test_claude_settings_are_created_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_home = Path(temp_dir)

            changed = ensure_claude_bypass_permissions(config_home)

            self.assertTrue(changed)
            data = json_from_file(claude_settings_path(config_home))
            self.assertEqual(data["permissions"]["defaultMode"], "bypassPermissions")

    def test_claude_settings_keep_existing_default_mode_untouched(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_home = Path(temp_dir)
            settings_path = claude_settings_path(config_home)
            settings_path.parent.mkdir(parents=True)
            original = '{"permissions":{"defaultMode":"ask"}}'
            settings_path.write_text(original, encoding="utf-8")

            changed = ensure_claude_bypass_permissions(config_home)

            self.assertFalse(changed)
            self.assertEqual(settings_path.read_text(encoding="utf-8"), original)

    def test_claude_settings_add_default_mode_to_existing_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_home = Path(temp_dir)
            settings_path = claude_settings_path(config_home)
            settings_path.parent.mkdir(parents=True)
            settings_path.write_text(
                '{"theme":"dark","permissions":{"allow":["Bash(git status)"]}}',
                encoding="utf-8",
            )

            changed = ensure_claude_bypass_permissions(config_home)

            self.assertTrue(changed)
            data = json_from_file(settings_path)
            self.assertEqual(data["theme"], "dark")
            self.assertEqual(data["permissions"]["allow"], ["Bash(git status)"])
            self.assertEqual(data["permissions"]["defaultMode"], "bypassPermissions")

    def test_claude_settings_invalid_json_is_not_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_home = Path(temp_dir)
            settings_path = claude_settings_path(config_home)
            settings_path.parent.mkdir(parents=True)
            original = "{not-json"
            settings_path.write_text(original, encoding="utf-8")

            with patch("sys.stderr", new=io.StringIO()):
                changed = ensure_claude_bypass_permissions(config_home)

            self.assertFalse(changed)
            self.assertEqual(settings_path.read_text(encoding="utf-8"), original)

    def test_build_command(self) -> None:
        command = make_build_command(
            docker_bin="docker",
            dockerfile=Path("Dockerfile"),
            context=Path("."),
            tag="yolo-agent:latest",
            build_args=["AGENT_CACHE_BUST=20260428"],
        )

        self.assertEqual(
            command,
            [
                "docker",
                "build",
                "--file",
                str(Path("Dockerfile")),
                "--tag",
                "yolo-agent:latest",
                "--build-arg",
                "AGENT_CACHE_BUST=20260428",
                ".",
            ],
        )

    def test_default_runtime_build_paths_use_launcher_dockerfile(self) -> None:
        paths = default_runtime_build_paths()

        self.assertEqual(paths.dockerfile.name, "Dockerfile")
        self.assertEqual(paths.dockerfile.parent.name, "runtime")
        self.assertTrue(paths.dockerfile.exists())
        self.assertTrue(paths.context.exists())

    def test_daily_cache_bust_uses_yyyymmdd(self) -> None:
        self.assertEqual(daily_cache_bust_value(date(2026, 4, 28)), "20260428")

    def test_build_args_include_daily_cache_bust_before_extra_args(self) -> None:
        args = make_build_args(
            extra_args=["FOO=bar"],
            agent_cache_bust=None,
            no_agent_cache_bust=False,
            today=date(2026, 4, 28),
        )

        self.assertEqual(args, ["AGENT_CACHE_BUST=20260428", "FOO=bar"])

    def test_build_args_can_disable_cache_bust(self) -> None:
        args = make_build_args(
            extra_args=["FOO=bar"],
            agent_cache_bust=None,
            no_agent_cache_bust=True,
            today=date(2026, 4, 28),
        )

        self.assertEqual(args, ["FOO=bar"])

    def test_build_is_enabled_by_default(self) -> None:
        self.assertTrue(resolve_build_enabled(None))
        self.assertFalse(resolve_build_enabled(False))

    def test_dind_reuse_is_enabled_by_default(self) -> None:
        self.assertTrue(resolve_dind_reuse(None))
        self.assertFalse(resolve_dind_reuse(False))

    def test_parse_duration_seconds(self) -> None:
        self.assertEqual(parse_duration_seconds("30m"), 1800)
        self.assertEqual(parse_duration_seconds("1h"), 3600)
        self.assertEqual(parse_duration_seconds("3600"), 3600)

    def test_stale_sidecar_records_skips_current_sidecar(self) -> None:
        records = {
            "agent-dind-current": {"last_used": 10, "run_volume": "current-run"},
            "agent-dind-old": {"last_used": 10, "run_volume": "old-run"},
            "agent-dind-new": {"last_used": 1000, "run_volume": "new-run"},
        }

        stale = stale_sidecar_records(records, exclude_name="agent-dind-current", cutoff=100)

        self.assertEqual(stale, [("agent-dind-old", {"last_used": 10, "run_volume": "old-run"})])

    def test_sidecar_state_round_trip(self) -> None:
        state_file = Path("C:/tmp/yolo-agent-test-state.json")
        state_file.unlink(missing_ok=True)
        try:
            save_sidecar_records(
                state_file,
                {"agent-dind-old": {"last_used": 10, "run_volume": "old-run"}},
            )

            self.assertEqual(
                load_sidecar_records(state_file),
                {"agent-dind-old": {"last_used": 10, "run_volume": "old-run"}},
            )
        finally:
            state_file.unlink(missing_ok=True)

    def test_record_sidecar_use_writes_current_sidecar(self) -> None:
        state_file = Path("C:/tmp/yolo-agent-test-record-state.json")
        state_file.unlink(missing_ok=True)
        config = RunConfig(
            docker_bin="docker",
            image="yolo-agent:latest",
            workspace="/workspace",
            host_cwd=Path("C:/project").resolve(),
            docker_mode="dind",
            dind_name="agent-dind-current",
            dind_run_volume="agent-dind-run-current",
            state_file=state_file,
        )

        try:
            record_sidecar_use(config)
            records = load_sidecar_records(state_file)

            self.assertIn("agent-dind-current", records)
            self.assertEqual(records["agent-dind-current"]["run_volume"], "agent-dind-run-current")
        finally:
            state_file.unlink(missing_ok=True)

    def test_normalize_remainder_strips_separator(self) -> None:
        self.assertEqual(
            normalize_remainder(["--", "bash", "-lc", "echo ok"]),
            ["bash", "-lc", "echo ok"],
        )

    def test_claude_shortcut_adds_yolo_flag(self) -> None:
        self.assertEqual(
            resolve_container_command(["claude", "--model", "sonnet"]),
            ["claude", "--dangerously-skip-permissions", "--model", "sonnet"],
        )

    def test_codex_shortcut_adds_yolo_flag(self) -> None:
        self.assertEqual(
            resolve_container_command(["codex", "--model", "gpt-5.2"]),
            ["codex", "--dangerously-bypass-approvals-and-sandbox", "--model", "gpt-5.2"],
        )

    def test_separator_bypasses_tool_shortcut_expansion(self) -> None:
        self.assertEqual(resolve_container_command(["--", "claude"]), ["claude"])

    def test_unknown_container_command_is_unchanged(self) -> None:
        self.assertEqual(resolve_container_command(["bash", "-lc", "echo ok"]), ["bash", "-lc", "echo ok"])


def json_from_file(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


if __name__ == "__main__":
    unittest.main()
