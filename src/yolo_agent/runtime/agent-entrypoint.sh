#!/usr/bin/env bash
set -Eeuo pipefail

AGENT_USER="${AGENT_USER:-agent}"
AGENT_HOME="${AGENT_HOME:-/home/agent}"

if [[ $# -eq 0 ]]; then
  set -- /bin/bash
fi

configure_claude_permissions() {
  local claude_dir="${AGENT_HOME}/.claude"
  mkdir -p "${claude_dir}"
  printf '%s\n' '{"permissions":{"defaultMode":"bypassPermissions"}}' > "${claude_dir}/settings.json"
  chown -R "${AGENT_USER}:${AGENT_USER}" "${claude_dir}" >/dev/null 2>&1 || true
}

if [[ "$(id -u)" == "0" ]]; then
  mkdir -p "${AGENT_HOME}"
  chown "${AGENT_USER}:${AGENT_USER}" "${AGENT_HOME}" >/dev/null 2>&1 || true
  configure_claude_permissions

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
