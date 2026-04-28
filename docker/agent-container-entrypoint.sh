#!/usr/bin/env bash
set -Eeuo pipefail

if [[ $# -eq 0 ]]; then
  set -- bash
fi

DOCKERD_PID=""
DOCKERD_LOG="${AGENT_DOCKERD_LOG:-/tmp/agent-dockerd.log}"

cleanup() {
  local status=$?
  if [[ -n "${DOCKERD_PID}" ]] && kill -0 "${DOCKERD_PID}" >/dev/null 2>&1; then
    kill "${DOCKERD_PID}" >/dev/null 2>&1 || true
    wait "${DOCKERD_PID}" >/dev/null 2>&1 || true
  fi
  exit "${status}"
}

start_dockerd() {
  if docker info >/dev/null 2>&1; then
    return 0
  fi

  mkdir -p /var/lib/docker /var/run
  rm -f /var/run/docker.pid

  dockerd \
    --host=unix:///var/run/docker.sock \
    --data-root=/var/lib/docker \
    >"${DOCKERD_LOG}" 2>&1 &
  DOCKERD_PID=$!

  for _ in $(seq 1 "${AGENT_DOCKERD_WAIT_SECONDS:-60}"); do
    if docker info >/dev/null 2>&1; then
      return 0
    fi

    if ! kill -0 "${DOCKERD_PID}" >/dev/null 2>&1; then
      echo "dockerd exited before becoming ready. Log follows:" >&2
      cat "${DOCKERD_LOG}" >&2 || true
      return 1
    fi

    sleep 1
  done

  echo "timed out waiting for dockerd. Log follows:" >&2
  cat "${DOCKERD_LOG}" >&2 || true
  return 1
}

case "${AGENT_DOCKER_MODE:-dind}" in
  dind)
    trap cleanup EXIT INT TERM
    start_dockerd
    ;;
  socket|none)
    ;;
  *)
    echo "unknown AGENT_DOCKER_MODE: ${AGENT_DOCKER_MODE}" >&2
    exit 2
    ;;
esac

"$@"
