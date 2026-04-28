# YOLO Agent Launcher

`agent` is a small Windows-friendly Python CLI that starts the current directory
inside a Docker-based agent environment.

The default mode is real Docker-in-Docker (`dind`): the outer container starts
its own Docker daemon, so test suites inside the agent container can run Docker
or Docker Compose without talking to the host daemon.

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

This builds `docker/Dockerfile` as `yolo-agent:latest`.

## Run from any project directory

```powershell
cd C:\path\to\some-project
agent
```

The launcher runs roughly this shape of command:

```powershell
docker run --rm -it --privileged `
  --mount type=bind,source="$PWD",target=/workspace `
  --workdir /workspace `
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

This is the default. The container is started with `--privileged`, and the
example image starts `dockerd` inside the container.

Use this when project tests run nested Docker containers and expect bind mounts
from paths like `/workspace` to work.

Optionally persist nested Docker state:

```powershell
agent --docker-mode dind --dind-volume yolo-agent-dind-cache
```

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
agent --build --dockerfile Dockerfile.agent --context .
agent -e FOO=bar -p 8080:8080
agent --dry-run
```

## Custom runtime images

To support `--docker-mode dind`, the image needs:

- a Docker CLI
- a Docker daemon (`dockerd`)
- an entrypoint that starts `dockerd` before running the requested command

The included `docker/Dockerfile` and `docker/agent-container-entrypoint.sh` are a
minimal reference. If you already have a larger demo Dockerfile, copy the
entrypoint behavior into it or use this Dockerfile as the base and add your
tools on top.
