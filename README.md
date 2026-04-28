# YOLO Agent Launcher

`agent` is a small Windows-friendly Python CLI that starts the current directory
inside a Docker-based agent environment.

The default mode is real Docker-in-Docker (`dind`) using a reusable sidecar
daemon:

1. reuse a ready workspace-scoped `docker:dind` container when one exists
2. otherwise start a privileged `docker:dind` container
3. mount the user's current directory into that daemon container
4. start the agent container with the same workspace mount
5. share the sidecar daemon's `/var/run/docker.sock` and network namespace with
   the agent container

That means the agent image only needs the Docker CLI. It does not need to run
`dockerd` itself. The first run in a workspace waits for Docker-in-Docker to
become ready; later runs reuse the already-ready daemon.

## Install for local development

```powershell
py -m pip install -e .
```

After that, `agent` should be available on PATH for the active Python
environment.

For a more global Windows install, use `pipx`:

```powershell
uvx pipx install . --force
```

## Build the runtime image

```powershell
agent --no-run
```

`agent` builds the runtime image by default before it starts the container. The
packaged runtime `Dockerfile` is built as `yolo-agent:latest` unless `--image`
or `--tag` is changed. The default Dockerfile is fixed to
`src/yolo_agent/runtime/Dockerfile` in this checkout, and to the same bundled
file after packaging. It is not taken from the repository root or from the
user's current project directory.

Every build automatically includes a daily cache-bust argument:

```powershell
docker build --file C:\xsoft\yolo_agent\src\yolo_agent\runtime\Dockerfile `
  --tag yolo-agent:latest `
  --build-arg AGENT_CACHE_BUST=20260428 `
  C:\xsoft\yolo_agent\src\yolo_agent\runtime
```

The value is the current local date in `YYYYMMDD` form. This means the first
`agent` run each day refreshes the Dockerfile layers after `ARG
AGENT_CACHE_BUST`; later runs on the same day reuse Docker cache.

Skip the default build when needed:

```powershell
agent --no-build
```

## Run from any project directory

```powershell
cd C:\path\to\some-project
agent
```

The launcher runs roughly this shape of command:

```powershell
docker build --file C:\xsoft\yolo_agent\src\yolo_agent\runtime\Dockerfile `
  --tag yolo-agent:latest `
  --build-arg AGENT_CACHE_BUST=20260428 `
  C:\xsoft\yolo_agent\src\yolo_agent\runtime

docker exec agent-dind-... docker info

docker volume create agent-dind-run-...

docker run -d --privileged `
  --name agent-dind-... `
  -e DOCKER_TLS_CERTDIR= `
  -e DOCKER_DRIVER=overlay2 `
  -v agent-dind-run-...:/var/run `
  --mount type=bind,source="$PWD",target=/workspace-some-project `
  docker:dind --host=unix:///var/run/docker.sock

docker run --rm -it `
  --workdir /workspace-some-project `
  --mount type=bind,source="$PWD",target=/workspace-some-project `
  -v agent-dind-run-...:/var/run `
  --network container:agent-dind-... `
  --env AGENT_DOCKER_MODE=dind `
  --env DOCKER_HOST=unix:///var/run/docker.sock `
  yolo-agent:latest
```

Inside the container, the default work directory is based on the folder name
where the user ran `agent`. For example, running from `C:\path\to\some-project`
mounts that folder at `/workspace-some-project`. Override it with
`--workspace` when a fixed path is needed.

The agent container runs commands as the non-root `agent` user. A root
entrypoint performs startup setup, fixes Docker socket group access, then drops
to that user. This is required for tools such as `claude
--dangerously-skip-permissions`, which refuse to run as root.

Before the container starts, the launcher ensures the host-side Claude settings
file includes:

```json
{"permissions":{"defaultMode":"bypassPermissions"}}
```

in `%USERPROFILE%\.claude_docker\settings.json`. It preserves existing JSON and
does not rewrite the file when `permissions.defaultMode` already exists. If the
file is not valid JSON, the launcher prints a warning and leaves it untouched.
The runtime Dockerfile and container entrypoint do not write this settings file.

The agent container also mounts existing host agent config paths into the
non-root user's home:

```text
%USERPROFILE%\.codex              -> /home/agent/.codex
%USERPROFILE%\.gemini             -> /home/agent/.gemini
%USERPROFILE%\.claude_docker      -> /home/agent/.claude
%USERPROFILE%\.claude_docker.json -> /home/agent/.claude.json
```

Missing host paths are skipped. Disable these mounts with
`--no-config-mounts`.

The launcher also sets Docker-side uv storage defaults:

```text
UV_PROJECT_ENVIRONMENT=/home/agent/.local/share/yolo-agent/uv/project-envs/<project-token>
UV_CACHE_DIR=/home/agent/.local/share/yolo-agent/uv/cache
agent-uv-data -> /home/agent/.local/share/yolo-agent/uv
```

This keeps Linux virtual environments separate from any Windows host `.venv`,
persists them across agent container restarts, and keeps the uv cache on the
same Docker volume as the project environments. Override either variable with
`-e`, or disable both defaults with `--no-uv-defaults`.

## Run a command inside the agent container

```powershell
agent -- bash -lc "pwd && docker version"
```

Arguments after `--` are passed to the container command.

For common agent CLIs, the launcher provides shortcuts:

```powershell
agent claude
agent codex
```

`agent claude` runs `claude --dangerously-skip-permissions`. `agent codex` runs
`codex --dangerously-bypass-approvals-and-sandbox`. Extra arguments are passed
through after the default YOLO flag, for example `agent codex --model gpt-5.2`.
Use `agent -- claude ...` or `agent -- codex ...` to run the raw command without
shortcut expansion.

## Docker modes

### `dind`

```powershell
agent --docker-mode dind
```

This is the default. A workspace-scoped privileged `docker:dind` sidecar is
started when needed, and the agent container talks to that daemon through a
shared Unix socket.

Use this when project tests run nested Docker containers and expect bind mounts
from paths like `/workspace-some-project` to work.

The sidecar is reused by default, so the roughly 15 second DinD startup cost is
paid only the first time for a workspace. Nested Docker images and containers
also remain available while the sidecar is running.

Each normal `agent` run also cleans old reused sidecars before starting the
current one. The launcher records sidecar usage in a local state file and
removes sidecars idle for more than one hour, except the sidecar that is about
to be used. If a sidecar still has a running agent container attached to it,
cleanup skips it.

On Windows, the state file defaults to
`%LOCALAPPDATA%\yolo-agent\state.json`.

Optionally persist nested Docker state:

```powershell
agent --docker-mode dind --dind-volume yolo-agent-dind-cache
```

Use a pinned sidecar daemon image:

```powershell
agent --docker-mode dind --dind-image docker:29-dind
```

Keep the sidecar daemon around for debugging:

```powershell
agent --docker-mode dind --keep-dind
```

Force a fresh sidecar for one run:

```powershell
agent --docker-mode dind --no-dind-reuse
```

Reset or stop the reusable sidecar for the current workspace:

```powershell
agent --reset-dind
agent --stop-dind
```

Adjust or disable idle cleanup:

```powershell
agent --dind-idle-timeout 30m
agent --no-dind-idle-cleanup
```

Published ports are part of the reusable sidecar identity. If you change `-p`
values, `agent` uses a separate sidecar for that port set.

### `inline-dind`

```powershell
agent --docker-mode inline-dind
```

This starts the agent container itself with `--privileged`. Use this only when
the agent image includes `dockerd` and its entrypoint starts the daemon. The
files under `docker/` are a minimal reference for this style.

### `socket`

```powershell
agent --docker-mode socket
```

This mounts `/var/run/docker.sock` from Docker Desktop into the container. It is
lighter, but it gives the container control over the host Docker daemon and can
break nested bind mounts when tools inside the container refer to the generated
workspace path such as `/workspace-some-project`.

Use this only when that tradeoff is acceptable.

### `none`

```powershell
agent --docker-mode none
```

This does not expose Docker inside the container.

## Useful options

```powershell
agent --image my-agent:dev
agent --tag my-agent:dev
agent --no-build
agent --dockerfile custom-agent.Dockerfile --context .
agent --agent-cache-bust 20260428
agent --no-agent-cache-bust
agent --build-arg FOO=bar
agent --no-dind-reuse
agent --reset-dind
agent --stop-dind
agent --dind-idle-timeout 30m
agent --no-dind-idle-cleanup
agent --no-config-mounts
agent -e FOO=bar -p 8080:8080
agent --clear-entrypoint -- bash -lc "docker version"
agent --dry-run
```

## Custom runtime images

To support the default `--docker-mode dind`, the agent image needs:

- a Docker CLI

The packaged runtime `Dockerfile` is the current runtime image definition. It
installs common developer tools plus Docker CLI/Buildx/Compose, which is enough
for sidecar DinD.

The launcher passes `AGENT_CACHE_BUST=YYYYMMDD` into this Dockerfile by default.
The Dockerfile writes that value before installing agent CLIs, so the install
layers are refreshed once per day.

Prefer `CMD ["bash"]` over `ENTRYPOINT ["bash"]` for runtime images. A bash
entrypoint makes explicit commands like `agent -- bash -lc "..."` awkward. If an
existing image already has an entrypoint, use `--clear-entrypoint` or
`--entrypoint`.

For `--docker-mode inline-dind`, the image also needs a Docker daemon
(`dockerd`) and an entrypoint that starts it before running the requested
command.
