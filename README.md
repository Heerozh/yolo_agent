# YOLO Agent Launcher

`agent` is a small Windows-friendly Python CLI that starts the current directory
inside a Docker-based agent environment.

The default mode is real Docker-in-Docker (`dind`) using a sidecar daemon:

1. start a temporary privileged `docker:dind` container
2. mount the user's current directory into that daemon container
3. start the agent container with the same workspace mount
4. share the sidecar daemon's `/var/run/docker.sock` and network namespace with
   the agent container

That means the agent image only needs the Docker CLI. It does not need to run
`dockerd` itself.

## Install for local development

```powershell
py -m pip install -e .
```

After that, `agent` should be available on PATH for the active Python
environment.

For a more global Windows install, use `pipx`:

```powershell
pipx install .
```

## Build the runtime image

```powershell
agent --build --no-run
```

This builds the root `Dockerfile` as `yolo-agent:latest`.

## Run from any project directory

```powershell
cd C:\path\to\some-project
agent
```

The launcher runs roughly this shape of command:

```powershell
docker volume create agent-dind-run-...

docker run -d --rm --privileged `
  --name agent-dind-... `
  -e DOCKER_TLS_CERTDIR= `
  -e DOCKER_DRIVER=overlay2 `
  -v agent-dind-run-...:/var/run `
  --mount type=bind,source="$PWD",target=/workspace `
  docker:dind --host=unix:///var/run/docker.sock

docker run --rm -it `
  --workdir /workspace `
  --mount type=bind,source="$PWD",target=/workspace `
  -v agent-dind-run-...:/var/run `
  --network container:agent-dind-... `
  --env AGENT_DOCKER_MODE=dind `
  --env DOCKER_HOST=unix:///var/run/docker.sock `
  yolo-agent:latest
```

Inside the container, `/workspace` is the directory where the user ran
`agent`.

## Run a command inside the agent container

```powershell
agent -- bash -lc "pwd && docker version"
```

Arguments after `--` are passed to the container command.

## Docker modes

### `dind`

```powershell
agent --docker-mode dind
```

This is the default. A temporary privileged `docker:dind` sidecar is started,
and the agent container talks to that daemon through a shared Unix socket.

Use this when project tests run nested Docker containers and expect bind mounts
from paths like `/workspace` to work.

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
break nested bind mounts when tools inside the container refer to `/workspace`.

Use this only when that tradeoff is acceptable.

### `none`

```powershell
agent --docker-mode none
```

This does not expose Docker inside the container.

## Useful options

```powershell
agent --image my-agent:dev
agent --build --dockerfile Dockerfile --context .
agent -e FOO=bar -p 8080:8080
agent --clear-entrypoint -- bash -lc "docker version"
agent --dry-run
```

## Custom runtime images

To support the default `--docker-mode dind`, the agent image needs:

- a Docker CLI

The root `Dockerfile` is the current demo runtime image. It installs common
developer tools plus Docker CLI/Buildx/Compose, which is enough for sidecar
DinD.

Prefer `CMD ["bash"]` over `ENTRYPOINT ["bash"]` for runtime images. A bash
entrypoint makes explicit commands like `agent -- bash -lc "..."` awkward. If an
existing image already has an entrypoint, use `--clear-entrypoint` or
`--entrypoint`.

For `--docker-mode inline-dind`, the image also needs a Docker daemon
(`dockerd`) and an entrypoint that starts it before running the requested
command.
