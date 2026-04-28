from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from yolo_agent.cli import (
    RunConfig,
    make_build_command,
    make_run_command,
    normalize_remainder,
)


class CliCommandTests(unittest.TestCase):
    def test_dind_mode_adds_privileged_and_workspace_mount(self) -> None:
        config = RunConfig(
            docker_bin="docker",
            image="yolo-agent:latest",
            workspace="/workspace",
            host_cwd=Path("C:/project").resolve(),
            docker_mode="dind",
            command=["bash"],
        )

        with patch.object(sys.stdin, "isatty", return_value=True), patch.object(
            sys.stdout, "isatty", return_value=True
        ):
            command = make_run_command(config)

        self.assertIn("--privileged", command)
        self.assertIn("--tty", command)
        self.assertIn("--interactive", command)
        self.assertIn("AGENT_DOCKER_MODE=dind", command)
        self.assertIn("DOCKER_HOST=unix:///var/run/docker.sock", command)
        self.assertIn("bash", command)

        mount_index = command.index("--mount")
        self.assertEqual(
            command[mount_index + 1],
            f"type=bind,source={Path('C:/project').resolve()},target=/workspace",
        )

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

    def test_build_command(self) -> None:
        command = make_build_command(
            docker_bin="docker",
            dockerfile=Path("docker/Dockerfile"),
            context=Path("."),
            tag="yolo-agent:latest",
        )

        self.assertEqual(
            command,
            [
                "docker",
                "build",
                "--file",
                str(Path("docker/Dockerfile")),
                "--tag",
                "yolo-agent:latest",
                ".",
            ],
        )

    def test_normalize_remainder_strips_separator(self) -> None:
        self.assertEqual(normalize_remainder(["--", "bash", "-lc", "echo ok"]), ["bash", "-lc", "echo ok"])


if __name__ == "__main__":
    unittest.main()
