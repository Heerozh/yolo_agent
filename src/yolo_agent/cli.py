from __future__ import annotations

import argparse
import os
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence


DEFAULT_IMAGE = "yolo-agent:latest"
DEFAULT_DOCKERFILE = "docker/Dockerfile"
DEFAULT_WORKSPACE = "/workspace"


@dataclass(frozen=True)
class RunConfig:
    docker_bin: str
    image: str
    workspace: str
    host_cwd: Path
    docker_mode: str
    command: list[str] = field(default_factory=list)
    env: list[str] = field(default_factory=list)
    volumes: list[str] = field(default_factory=list)
    ports: list[str] = field(default_factory=list)
    run_args: list[str] = field(default_factory=list)
    name: str | None = None
    dind_volume: str | None = None
    keep_container: bool = False
    no_tty: bool = False
    no_stdin: bool = False
    pull: str = "missing"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent",
        description="Run the current directory inside a Docker-based agent environment.",
    )
    parser.add_argument(
        "--image",
        default=os.environ.get("AGENT_IMAGE", DEFAULT_IMAGE),
        help=f"Runtime image to run. Default: {DEFAULT_IMAGE}",
    )
    parser.add_argument(
        "--workspace",
        default=os.environ.get("AGENT_WORKSPACE", DEFAULT_WORKSPACE),
        help=f"Container workspace path. Default: {DEFAULT_WORKSPACE}",
    )
    parser.add_argument(
        "--docker-mode",
        choices=("dind", "socket", "none"),
        default=os.environ.get("AGENT_DOCKER_MODE", "dind"),
        help="How Docker should be made available inside the agent container.",
    )
    parser.add_argument(
        "--docker-bin",
        default=os.environ.get("AGENT_DOCKER_BIN", "docker"),
        help="Docker executable to call on the host. Default: docker",
    )
    parser.add_argument(
        "--name",
        help="Optional container name.",
    )
    parser.add_argument(
        "-e",
        "--env",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Environment variable passed to the agent container. Repeatable.",
    )
    parser.add_argument(
        "-v",
        "--volume",
        action="append",
        default=[],
        metavar="SPEC",
        help="Additional raw Docker volume spec. Repeatable.",
    )
    parser.add_argument(
        "-p",
        "--publish",
        action="append",
        default=[],
        metavar="SPEC",
        help="Port publishing spec, for example 8080:8080. Repeatable.",
    )
    parser.add_argument(
        "--run-arg",
        action="append",
        default=[],
        metavar="ARG",
        help="Extra raw docker run argument. Repeatable.",
    )
    parser.add_argument(
        "--dind-volume",
        metavar="VOLUME",
        help="Persist nested Docker data in this Docker volume at /var/lib/docker.",
    )
    parser.add_argument(
        "--keep",
        action="store_true",
        help="Do not remove the agent container after it exits.",
    )
    parser.add_argument(
        "--no-tty",
        action="store_true",
        help="Do not allocate a pseudo-TTY.",
    )
    parser.add_argument(
        "--no-stdin",
        action="store_true",
        help="Do not keep STDIN open for the container.",
    )
    parser.add_argument(
        "--pull",
        choices=("always", "missing", "never"),
        default=os.environ.get("AGENT_PULL", "missing"),
        help="Docker image pull policy for docker run. Default: missing",
    )
    parser.add_argument(
        "--build",
        action="store_true",
        help="Build the runtime image before running it.",
    )
    parser.add_argument(
        "--no-run",
        action="store_true",
        help="Build or print commands without running the agent container.",
    )
    parser.add_argument(
        "--dockerfile",
        default=DEFAULT_DOCKERFILE,
        help=f"Dockerfile used with --build. Default: {DEFAULT_DOCKERFILE}",
    )
    parser.add_argument(
        "--context",
        default=".",
        help="Build context used with --build. Default: current project.",
    )
    parser.add_argument(
        "--tag",
        default=DEFAULT_IMAGE,
        help=f"Image tag used with --build. Default: {DEFAULT_IMAGE}",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print Docker commands without executing them.",
    )
    parser.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        help="Optional command to run inside the container. Use -- before commands that start with '-'.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not shutil.which(args.docker_bin):
        print(
            f"agent: Docker executable not found: {args.docker_bin!r}. "
            "Install Docker Desktop or set AGENT_DOCKER_BIN.",
            file=sys.stderr,
        )
        return 127

    if args.pull not in {"always", "missing", "never"}:
        print("agent: --pull must be one of: always, missing, never", file=sys.stderr)
        return 2

    command = normalize_remainder(args.command)
    host_cwd = Path.cwd().resolve()

    if args.build:
        build_cmd = make_build_command(
            docker_bin=args.docker_bin,
            dockerfile=Path(args.dockerfile),
            context=Path(args.context),
            tag=args.tag,
        )
        if args.dry_run:
            print(format_command(build_cmd))
        else:
            build_result = subprocess.run(build_cmd)
            if build_result.returncode != 0:
                return build_result.returncode

    if args.no_run:
        return 0

    image = args.image
    if args.build and args.image == DEFAULT_IMAGE:
        image = args.tag

    config = RunConfig(
        docker_bin=args.docker_bin,
        image=image,
        workspace=args.workspace,
        host_cwd=host_cwd,
        docker_mode=args.docker_mode,
        command=command,
        env=args.env,
        volumes=args.volume,
        ports=args.publish,
        run_args=args.run_arg,
        name=args.name,
        dind_volume=args.dind_volume,
        keep_container=args.keep,
        no_tty=args.no_tty,
        no_stdin=args.no_stdin,
        pull=args.pull,
    )
    run_cmd = make_run_command(config)

    if args.dry_run:
        print(format_command(run_cmd))
        return 0

    try:
        return subprocess.run(run_cmd).returncode
    except KeyboardInterrupt:
        return 130


def normalize_remainder(command: list[str]) -> list[str]:
    if command and command[0] == "--":
        return command[1:]
    return command


def make_build_command(
    *,
    docker_bin: str,
    dockerfile: Path,
    context: Path,
    tag: str,
) -> list[str]:
    return [
        docker_bin,
        "build",
        "--file",
        str(dockerfile),
        "--tag",
        tag,
        str(context),
    ]


def make_run_command(config: RunConfig) -> list[str]:
    cmd = [config.docker_bin, "run"]

    if not config.keep_container:
        cmd.append("--rm")

    if not config.no_stdin:
        cmd.append("--interactive")
    if should_allocate_tty(config.no_tty):
        cmd.append("--tty")

    if config.name:
        cmd.extend(["--name", config.name])

    if config.pull != "never":
        cmd.extend(["--pull", config.pull])

    add_workspace_mount(cmd, config.host_cwd, config.workspace)
    cmd.extend(["--workdir", config.workspace])
    cmd.extend(["--env", f"AGENT_HOST_CWD={config.host_cwd}"])
    cmd.extend(["--env", f"AGENT_WORKSPACE={config.workspace}"])

    apply_docker_mode(cmd, config)

    for item in config.env:
        cmd.extend(["--env", item])
    for volume in config.volumes:
        cmd.extend(["--volume", volume])
    for port in config.ports:
        cmd.extend(["--publish", port])
    for arg in config.run_args:
        cmd.append(arg)

    cmd.append(config.image)
    cmd.extend(config.command)
    return cmd


def should_allocate_tty(no_tty: bool) -> bool:
    return not no_tty and sys.stdin.isatty() and sys.stdout.isatty()


def add_workspace_mount(cmd: list[str], host_cwd: Path, workspace: str) -> None:
    cmd.extend(
        [
            "--mount",
            f"type=bind,source={host_cwd},target={workspace}",
        ]
    )


def apply_docker_mode(cmd: list[str], config: RunConfig) -> None:
    if config.docker_mode == "none":
        cmd.extend(["--env", "AGENT_DOCKER_MODE=none"])
        return

    cmd.extend(["--env", f"AGENT_DOCKER_MODE={config.docker_mode}"])
    cmd.extend(["--env", "DOCKER_HOST=unix:///var/run/docker.sock"])

    if config.docker_mode == "dind":
        cmd.append("--privileged")
        if config.dind_volume:
            cmd.extend(["--volume", f"{config.dind_volume}:/var/lib/docker"])
        return

    if config.docker_mode == "socket":
        cmd.extend(
            [
                "--mount",
                "type=bind,source=/var/run/docker.sock,target=/var/run/docker.sock",
            ]
        )
        return

    raise ValueError(f"unknown docker mode: {config.docker_mode}")


def format_command(command: Sequence[str]) -> str:
    return " ".join(shell_quote(part) for part in command)


def shell_quote(value: str) -> str:
    if os.name == "nt":
        return subprocess.list2cmdline([value])
    return shlex.quote(value)


if __name__ == "__main__":
    raise SystemExit(main())
