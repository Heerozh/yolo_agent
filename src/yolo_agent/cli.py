from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Sequence


DEFAULT_IMAGE = "yolo-agent:latest"
DEFAULT_DOCKERFILE = "Dockerfile"
DEFAULT_WORKSPACE = "/workspace"
DEFAULT_DIND_IMAGE = "docker:dind"
DEFAULT_DIND_IDLE_TIMEOUT = "1h"
FALSE_VALUES = {"0", "false", "no", "off"}


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
    entrypoint: str | None = None
    clear_entrypoint: bool = False
    dind_image: str = DEFAULT_DIND_IMAGE
    dind_name: str | None = None
    dind_run_volume: str | None = None
    dind_volume: str | None = None
    dind_reuse: bool = True
    reset_dind: bool = False
    dind_idle_cleanup: bool = True
    dind_idle_timeout_seconds: int = 3600
    state_file: Path | None = None
    keep_dind: bool = False
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
        choices=("dind", "inline-dind", "socket", "none"),
        default=os.environ.get("AGENT_DOCKER_MODE", "dind"),
        help=(
            "How Docker should be made available inside the agent container. "
            "'dind' starts a sidecar docker:dind daemon."
        ),
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
        "--entrypoint",
        help="Override the runtime image entrypoint.",
    )
    parser.add_argument(
        "--clear-entrypoint",
        action="store_true",
        help="Clear the runtime image entrypoint before running the command.",
    )
    parser.add_argument(
        "--dind-volume",
        metavar="VOLUME",
        help="Persist sidecar/inline DinD data in this Docker volume at /var/lib/docker.",
    )
    parser.add_argument(
        "--dind-image",
        default=os.environ.get("AGENT_DIND_IMAGE", DEFAULT_DIND_IMAGE),
        help=f"Sidecar DinD image used by --docker-mode dind. Default: {DEFAULT_DIND_IMAGE}",
    )
    parser.add_argument(
        "--dind-name",
        help="Optional name for the sidecar DinD container.",
    )
    parser.add_argument(
        "--dind-run-volume",
        help="Optional Docker volume name used to share /var/run with the sidecar DinD container.",
    )
    parser.add_argument(
        "--dind-reuse",
        dest="dind_reuse",
        action="store_true",
        default=None,
        help="Reuse a workspace-scoped sidecar DinD daemon. This is the default.",
    )
    parser.add_argument(
        "--no-dind-reuse",
        dest="dind_reuse",
        action="store_false",
        help="Start a fresh sidecar DinD daemon and remove it after the agent exits.",
    )
    parser.add_argument(
        "--reset-dind",
        action="store_true",
        help="Remove the workspace-scoped sidecar DinD daemon before running.",
    )
    parser.add_argument(
        "--stop-dind",
        action="store_true",
        help="Stop the workspace-scoped sidecar DinD daemon and exit.",
    )
    parser.add_argument(
        "--keep-dind",
        action="store_true",
        help="Do not stop a non-reused sidecar DinD container or remove its /var/run volume.",
    )
    parser.add_argument(
        "--dind-idle-timeout",
        default=os.environ.get("AGENT_DIND_IDLE_TIMEOUT", DEFAULT_DIND_IDLE_TIMEOUT),
        metavar="DURATION",
        help=f"Clean reused sidecars idle longer than this. Default: {DEFAULT_DIND_IDLE_TIMEOUT}.",
    )
    parser.add_argument(
        "--no-dind-idle-cleanup",
        action="store_true",
        help="Do not clean idle reused sidecars before starting the agent.",
    )
    parser.add_argument(
        "--state-file",
        default=os.environ.get("AGENT_STATE_FILE"),
        help=argparse.SUPPRESS,
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
        dest="build",
        action="store_true",
        default=None,
        help="Build the runtime image before running it. This is the default.",
    )
    parser.add_argument(
        "--no-build",
        dest="build",
        action="store_false",
        help="Skip the default runtime image build before running.",
    )
    parser.add_argument(
        "--no-run",
        action="store_true",
        help="Build or print commands without running the agent container.",
    )
    parser.add_argument(
        "--dockerfile",
        default=DEFAULT_DOCKERFILE,
        help=f"Dockerfile used for the runtime image build. Default: {DEFAULT_DOCKERFILE}",
    )
    parser.add_argument(
        "--context",
        default=".",
        help="Build context used for the runtime image build. Default: current project.",
    )
    parser.add_argument(
        "--tag",
        help="Image tag used for the runtime image build. Default: same as --image.",
    )
    parser.add_argument(
        "--build-arg",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Extra Docker build argument. Repeatable.",
    )
    parser.add_argument(
        "--agent-cache-bust",
        default=os.environ.get("AGENT_CACHE_BUST"),
        metavar="VALUE",
        help="Value passed as AGENT_CACHE_BUST. Default: today's local date as YYYYMMDD.",
    )
    parser.add_argument(
        "--no-agent-cache-bust",
        action="store_true",
        help="Do not pass the automatic AGENT_CACHE_BUST build argument.",
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

    try:
        dind_idle_timeout_seconds = parse_duration_seconds(args.dind_idle_timeout)
    except ValueError as exc:
        print(f"agent: invalid --dind-idle-timeout: {exc}", file=sys.stderr)
        return 2

    command = normalize_remainder(args.command)
    host_cwd = Path.cwd().resolve()
    should_build = resolve_build_enabled(args.build)
    build_tag = args.tag or args.image
    build_args = make_build_args(
        extra_args=args.build_arg,
        agent_cache_bust=args.agent_cache_bust,
        no_agent_cache_bust=args.no_agent_cache_bust,
    )

    image = args.image
    if should_build and args.tag and args.image == DEFAULT_IMAGE:
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
        entrypoint=args.entrypoint,
        clear_entrypoint=args.clear_entrypoint,
        dind_image=args.dind_image,
        dind_name=args.dind_name,
        dind_run_volume=args.dind_run_volume,
        dind_volume=args.dind_volume,
        dind_reuse=resolve_dind_reuse(args.dind_reuse),
        reset_dind=args.reset_dind,
        dind_idle_cleanup=not args.no_dind_idle_cleanup,
        dind_idle_timeout_seconds=dind_idle_timeout_seconds,
        state_file=Path(args.state_file) if args.state_file else default_state_file(),
        keep_dind=args.keep_dind,
        keep_container=args.keep,
        no_tty=args.no_tty,
        no_stdin=args.no_stdin,
        pull=args.pull,
    )

    if args.stop_dind:
        return stop_sidecar_dind(config, dry_run=args.dry_run)

    if should_build:
        build_cmd = make_build_command(
            docker_bin=args.docker_bin,
            dockerfile=Path(args.dockerfile),
            context=Path(args.context),
            tag=build_tag,
            build_args=build_args,
        )
        if args.dry_run:
            print(format_command(build_cmd))
        else:
            build_result = subprocess.run(build_cmd)
            if build_result.returncode != 0:
                return build_result.returncode

    if args.no_run:
        return 0

    return run_agent(config, dry_run=args.dry_run)


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
    build_args: Sequence[str] = (),
) -> list[str]:
    command = [
        docker_bin,
        "build",
        "--file",
        str(dockerfile),
        "--tag",
        tag,
    ]
    for build_arg in build_args:
        command.extend(["--build-arg", build_arg])
    command.append(str(context))
    return command


def resolve_build_enabled(cli_value: bool | None) -> bool:
    if cli_value is not None:
        return cli_value
    return parse_bool(os.environ.get("AGENT_AUTO_BUILD"), default=True)


def resolve_dind_reuse(cli_value: bool | None) -> bool:
    if cli_value is not None:
        return cli_value
    return parse_bool(os.environ.get("AGENT_DIND_REUSE"), default=True)


def parse_bool(value: str | None, *, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() not in FALSE_VALUES


def parse_duration_seconds(value: str) -> int:
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)([smhd]?)\s*", value.lower())
    if not match:
        raise ValueError(f"{value!r} is not a duration like 30m, 1h, or 3600")

    amount = float(match.group(1))
    unit = match.group(2)
    multiplier = {
        "": 1,
        "s": 1,
        "m": 60,
        "h": 3600,
        "d": 86400,
    }[unit]
    return int(amount * multiplier)


def make_build_args(
    *,
    extra_args: Sequence[str],
    agent_cache_bust: str | None,
    no_agent_cache_bust: bool,
    today: date | None = None,
) -> list[str]:
    build_args: list[str] = []
    if not no_agent_cache_bust:
        cache_bust = agent_cache_bust or daily_cache_bust_value(today)
        build_args.append(f"AGENT_CACHE_BUST={cache_bust}")
    build_args.extend(extra_args)
    return build_args


def daily_cache_bust_value(today: date | None = None) -> str:
    return (today or date.today()).strftime("%Y%m%d")


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
    if config.docker_mode == "dind" and config.dind_name:
        cmd.extend(["--label", "yolo-agent.managed=true"])
        cmd.extend(["--label", "yolo-agent.role=agent"])
        cmd.extend(["--label", f"yolo-agent.sidecar={config.dind_name}"])

    for item in config.env:
        cmd.extend(["--env", item])
    for volume in config.volumes:
        cmd.extend(["--volume", volume])
    if not uses_sidecar_dind(config):
        for port in config.ports:
            cmd.extend(["--publish", port])
    for arg in config.run_args:
        cmd.append(arg)

    if config.clear_entrypoint:
        cmd.append("--entrypoint=")
    elif config.entrypoint:
        cmd.extend(["--entrypoint", config.entrypoint])

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

    container_mode = "dind" if config.docker_mode == "inline-dind" else config.docker_mode
    cmd.extend(["--env", f"AGENT_DOCKER_MODE={container_mode}"])
    cmd.extend(["--env", "DOCKER_HOST=unix:///var/run/docker.sock"])

    if config.docker_mode == "dind":
        if not config.dind_run_volume:
            raise ValueError("sidecar dind mode requires a dind_run_volume")
        cmd.extend(["--volume", f"{config.dind_run_volume}:/var/run"])
        if config.dind_name:
            cmd.extend(["--network", f"container:{config.dind_name}"])
        return

    if config.docker_mode == "inline-dind":
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


def run_agent(config: RunConfig, *, dry_run: bool) -> int:
    if config.docker_mode == "dind":
        return run_with_sidecar_dind(config, dry_run=dry_run)

    run_cmd = make_run_command(config)

    if dry_run:
        print(format_command(run_cmd))
        return 0

    try:
        return subprocess.run(run_cmd).returncode
    except KeyboardInterrupt:
        return 130


def run_with_sidecar_dind(config: RunConfig, *, dry_run: bool) -> int:
    planned = with_sidecar_names(config)
    create_volume_cmd = [
        planned.docker_bin,
        "volume",
        "create",
        planned.dind_run_volume or "",
    ]
    start_dind_cmd = make_sidecar_dind_command(planned)
    wait_cmd = [planned.docker_bin, "exec", planned.dind_name or "", "docker", "info"]
    run_cmd = make_run_command(planned)
    cleanup_cmds = make_sidecar_cleanup_commands(planned)

    if dry_run:
        if planned.reset_dind:
            print("# reset reusable DinD sidecar:")
            for command in cleanup_cmds:
                print(format_command(command))
        if planned.dind_idle_cleanup and planned.dind_reuse:
            print(
                f"# clean reused DinD sidecars idle for more than "
                f"{planned.dind_idle_timeout_seconds} seconds, except {planned.dind_name}:"
            )
        if planned.dind_reuse:
            print("# reuse existing DinD sidecar if this succeeds:")
            print(format_command(wait_cmd))
            print("# otherwise start it:")
        print(format_command(create_volume_cmd))
        print(format_command(start_dind_cmd))
        print("# wait until DinD is ready:")
        print(format_command(wait_cmd))
        print(format_command(run_cmd))
        if should_cleanup_dind_after_run(planned):
            print("# cleanup:")
            for command in cleanup_cmds:
                print(format_command(command))
        return 0

    try:
        if planned.dind_idle_cleanup and planned.dind_reuse:
            cleanup_idle_sidecars(planned)
        if not ensure_sidecar_dind(
            planned,
            create_volume_cmd=create_volume_cmd,
            start_dind_cmd=start_dind_cmd,
            cleanup_cmds=cleanup_cmds,
        ):
            return 1
        record_sidecar_use(planned)
        result = subprocess.run(run_cmd).returncode
        record_sidecar_use(planned)
        return result
    except KeyboardInterrupt:
        return 130
    finally:
        if should_cleanup_dind_after_run(planned):
            cleanup_sidecar(cleanup_cmds)


def with_sidecar_names(config: RunConfig) -> RunConfig:
    token = workspace_token(config.host_cwd, config.ports)
    suffix = token if config.dind_reuse else f"{token}-{os.getpid()}"
    dind_name = config.dind_name or f"agent-dind-{suffix}"
    run_volume = config.dind_run_volume or f"agent-dind-run-{suffix}"
    return RunConfig(
        docker_bin=config.docker_bin,
        image=config.image,
        workspace=config.workspace,
        host_cwd=config.host_cwd,
        docker_mode=config.docker_mode,
        command=config.command,
        env=config.env,
        volumes=config.volumes,
        ports=config.ports,
        run_args=config.run_args,
        name=config.name,
        entrypoint=config.entrypoint,
        clear_entrypoint=config.clear_entrypoint,
        dind_image=config.dind_image,
        dind_name=dind_name,
        dind_run_volume=run_volume,
        dind_volume=config.dind_volume,
        dind_reuse=config.dind_reuse,
        reset_dind=config.reset_dind,
        dind_idle_cleanup=config.dind_idle_cleanup,
        dind_idle_timeout_seconds=config.dind_idle_timeout_seconds,
        state_file=config.state_file,
        keep_dind=config.keep_dind,
        keep_container=config.keep_container,
        no_tty=config.no_tty,
        no_stdin=config.no_stdin,
        pull=config.pull,
    )


def workspace_token(host_cwd: Path, ports: Sequence[str] = ()) -> str:
    token_source = str(host_cwd).lower()
    if ports:
        token_source += "\nports=" + "\n".join(sorted(ports))
    digest = hashlib.sha256(token_source.encode("utf-8")).hexdigest()[:8]
    slug = re.sub(r"[^a-z0-9_.-]+", "-", host_cwd.name.lower()).strip("-.")
    return f"{slug or 'workspace'}-{digest}"[:48]


def make_sidecar_dind_command(config: RunConfig) -> list[str]:
    if not config.dind_name or not config.dind_run_volume:
        raise ValueError("sidecar dind command requires dind_name and dind_run_volume")

    cmd = [
        config.docker_bin,
        "run",
        "--detach",
    ]
    if should_cleanup_dind_after_run(config):
        cmd.append("--rm")

    cmd.extend(
        [
            "--privileged",
            "--name",
            config.dind_name,
            "--env",
            "DOCKER_TLS_CERTDIR=",
            "--env",
            "DOCKER_DRIVER=overlay2",
            "--volume",
            f"{config.dind_run_volume}:/var/run",
            "--mount",
            f"type=bind,source={config.host_cwd},target={config.workspace}",
            "--workdir",
            config.workspace,
            "--label",
            "yolo-agent.managed=true",
            "--label",
            "yolo-agent.role=dind",
            "--label",
            f"yolo-agent.run-volume={config.dind_run_volume}",
        ]
    )

    for port in config.ports:
        cmd.extend(["--publish", port])

    if config.dind_volume:
        cmd.extend(["--volume", f"{config.dind_volume}:/var/lib/docker"])

    cmd.append(config.dind_image)
    cmd.append("--host=unix:///var/run/docker.sock")
    return cmd


def ensure_sidecar_dind(
    config: RunConfig,
    *,
    create_volume_cmd: Sequence[str],
    start_dind_cmd: Sequence[str],
    cleanup_cmds: Sequence[Sequence[str]],
) -> bool:
    if config.reset_dind:
        cleanup_sidecar(cleanup_cmds)
        remove_sidecar_record(config)

    if config.dind_reuse:
        running = get_container_running_state(config)
        if running is True:
            if is_dind_ready(config):
                print(f"agent: reusing sidecar Docker daemon {config.dind_name}", file=sys.stderr)
                return True
            print("agent: existing sidecar Docker daemon is still starting...", file=sys.stderr)
            if wait_for_dind(config):
                return True
            print("agent: recreating unready sidecar Docker daemon...", file=sys.stderr)
            cleanup_sidecar(cleanup_cmds)
            remove_sidecar_record(config)
        elif running is False:
            cleanup_sidecar(cleanup_cmds)
            remove_sidecar_record(config)

    subprocess.run(list(create_volume_cmd), check=True)
    subprocess.run(list(start_dind_cmd), check=True)
    return wait_for_dind(config)


def stop_sidecar_dind(config: RunConfig, *, dry_run: bool) -> int:
    if config.docker_mode != "dind":
        print("agent: --stop-dind only applies to --docker-mode dind", file=sys.stderr)
        return 2

    planned = with_sidecar_names(config)
    cleanup_cmds = make_sidecar_cleanup_commands(planned)
    if dry_run:
        for command in cleanup_cmds:
            print(format_command(command))
        return 0

    cleanup_sidecar(cleanup_cmds)
    remove_sidecar_record(planned)
    return 0


def make_sidecar_cleanup_commands(config: RunConfig) -> list[list[str]]:
    return [
        [config.docker_bin, "rm", "-f", config.dind_name or ""],
        [config.docker_bin, "volume", "rm", config.dind_run_volume or ""],
    ]


def should_cleanup_dind_after_run(config: RunConfig) -> bool:
    return not config.dind_reuse and not config.keep_dind


def cleanup_idle_sidecars(config: RunConfig) -> None:
    records = load_sidecar_records(config.state_file)
    cutoff = time.time() - config.dind_idle_timeout_seconds
    changed = False

    for name, record in stale_sidecar_records(records, exclude_name=config.dind_name, cutoff=cutoff):
        if has_running_agent_for_sidecar(config.docker_bin, name):
            continue

        run_volume = str(record.get("run_volume") or "")
        cleanup_cmds: list[list[str]] = [[config.docker_bin, "rm", "-f", name]]
        if run_volume:
            cleanup_cmds.append([config.docker_bin, "volume", "rm", run_volume])

        print(f"agent: cleaning idle sidecar Docker daemon {name}", file=sys.stderr)
        cleanup_sidecar(cleanup_cmds)
        records.pop(name, None)
        changed = True

    if changed:
        save_sidecar_records(config.state_file, records)


def stale_sidecar_records(
    records: dict[str, dict[str, Any]],
    *,
    exclude_name: str | None,
    cutoff: float,
) -> list[tuple[str, dict[str, Any]]]:
    stale: list[tuple[str, dict[str, Any]]] = []
    for name, record in records.items():
        if name == exclude_name:
            continue

        last_used = record.get("last_used")
        if not isinstance(last_used, int | float):
            continue

        if last_used < cutoff:
            stale.append((name, record))
    return stale


def record_sidecar_use(config: RunConfig) -> None:
    if not config.dind_reuse or not config.dind_name:
        return

    records = load_sidecar_records(config.state_file)
    records[config.dind_name] = {
        "run_volume": config.dind_run_volume,
        "workspace": str(config.host_cwd),
        "ports": list(config.ports),
        "last_used": time.time(),
    }
    save_sidecar_records(config.state_file, records)


def remove_sidecar_record(config: RunConfig) -> None:
    if not config.dind_name:
        return

    records = load_sidecar_records(config.state_file)
    if config.dind_name in records:
        records.pop(config.dind_name, None)
        save_sidecar_records(config.state_file, records)


def load_sidecar_records(path: Path | None) -> dict[str, dict[str, Any]]:
    state = load_state(path)
    sidecars = state.get("sidecars")
    if not isinstance(sidecars, dict):
        return {}

    records: dict[str, dict[str, Any]] = {}
    for name, record in sidecars.items():
        if isinstance(name, str) and isinstance(record, dict):
            records[name] = record
    return records


def save_sidecar_records(path: Path | None, records: dict[str, dict[str, Any]]) -> None:
    save_state(path, {"sidecars": records})


def load_state(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    if isinstance(data, dict):
        return data
    return {}


def save_state(path: Path | None, state: dict[str, Any]) -> None:
    if path is None:
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f"{path.name}.tmp")
    temp_path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    temp_path.replace(path)


def default_state_file() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    else:
        base = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state")
    return base / "yolo-agent" / "state.json"


def get_container_running_state(config: RunConfig) -> bool | None:
    result = subprocess.run(
        [
            config.docker_bin,
            "inspect",
            "--format",
            "{{.State.Running}}",
            config.dind_name or "",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip().lower() == "true"


def has_running_agent_for_sidecar(docker_bin: str, sidecar_name: str) -> bool:
    result = subprocess.run(
        [
            docker_bin,
            "ps",
            "--quiet",
            "--filter",
            "label=yolo-agent.role=agent",
            "--filter",
            f"label=yolo-agent.sidecar={sidecar_name}",
        ],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and bool(result.stdout.strip())


def is_dind_ready(config: RunConfig) -> bool:
    result = subprocess.run(
        [config.docker_bin, "exec", config.dind_name or "", "docker", "info"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0


def wait_for_dind(config: RunConfig) -> bool:
    timeout_seconds = int(os.environ.get("AGENT_DIND_WAIT_SECONDS", "60"))
    wait_cmd = [config.docker_bin, "exec", config.dind_name or "", "docker", "info"]

    for attempt in range(timeout_seconds):
        result = subprocess.run(
            wait_cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if result.returncode == 0:
            return True

        if attempt == 0 or (attempt + 1) % 5 == 0:
            print("agent: waiting for sidecar Docker daemon...", file=sys.stderr)
        time.sleep(1)

    logs_cmd = [config.docker_bin, "logs", config.dind_name or ""]
    print("agent: sidecar Docker daemon did not become ready. Logs:", file=sys.stderr)
    subprocess.run(logs_cmd)
    return False


def cleanup_sidecar(cleanup_cmds: Sequence[Sequence[str]]) -> None:
    for command in cleanup_cmds:
        subprocess.run(
            list(command),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def uses_sidecar_dind(config: RunConfig) -> bool:
    return config.docker_mode == "dind" and bool(config.dind_run_volume)


def format_command(command: Sequence[str]) -> str:
    return " ".join(shell_quote(part) for part in command)


def shell_quote(value: str) -> str:
    if os.name == "nt":
        return subprocess.list2cmdline([value])
    return shlex.quote(value)


if __name__ == "__main__":
    raise SystemExit(main())
