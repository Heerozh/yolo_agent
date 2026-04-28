from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from yolo_agent.cli import (
    RunConfig,
    make_build_command,
    make_run_command,
    make_sidecar_dind_command,
    normalize_remainder,
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
            clear_entrypoint=True,
            command=["bash", "-lc", "echo ok"],
        )

        command = make_run_command(config)

        self.assertLess(command.index("--entrypoint="), command.index("yolo-agent:latest"))

    def test_build_command(self) -> None:
        command = make_build_command(
            docker_bin="docker",
            dockerfile=Path("Dockerfile"),
            context=Path("."),
            tag="yolo-agent:latest",
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
                ".",
            ],
        )

    def test_normalize_remainder_strips_separator(self) -> None:
        self.assertEqual(normalize_remainder(["--", "bash", "-lc", "echo ok"]), ["bash", "-lc", "echo ok"])


if __name__ == "__main__":
    unittest.main()
