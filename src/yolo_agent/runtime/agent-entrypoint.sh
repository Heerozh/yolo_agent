#!/usr/bin/env bash
set -Eeuo pipefail

AGENT_USER="${AGENT_USER:-agent}"
AGENT_HOME="${AGENT_HOME:-/home/agent}"

if [[ $# -eq 0 ]]; then
  set -- /bin/bash
fi

if [[ "$(id -u)" == "0" ]]; then
  mkdir -p "${AGENT_HOME}"
  chown "${AGENT_USER}:${AGENT_USER}" "${AGENT_HOME}" >/dev/null 2>&1 || true

  if [[ -S /var/run/docker.sock ]]; then
    socket_gid="$(stat -c '%g' /var/run/docker.sock)"
    if ! getent group "${socket_gid}" >/dev/null 2>&1; then
      groupadd --gid "${socket_gid}" docker-host >/dev/null 2>&1 || true
    fi

    socket_group="$(getent group "${socket_gid}" | cut -d: -f1)"
    usermod -aG "${socket_group}" "${AGENT_USER}" >/dev/null 2>&1 || true
    chmod g+rw /var/run/docker.sock >/dev/null 2>&1 || true
  fi

  exec gosu "${AGENT_USER}" "$@"
fi

exec "$@"
