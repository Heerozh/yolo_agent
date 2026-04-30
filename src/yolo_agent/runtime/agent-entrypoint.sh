#!/usr/bin/env bash
set -Eeuo pipefail

AGENT_USER="${AGENT_USER:-agent}"
AGENT_HOME="${AGENT_HOME:-/home/agent}"

if [[ $# -eq 0 ]]; then
  set -- /bin/bash
fi

prepare_writable_dir() {
  local path="$1"
  if [[ -n "${path}" ]]; then
    mkdir -p "${path}"
    chown -R "${AGENT_USER}:${AGENT_USER}" "${path}" >/dev/null 2>&1 || true
  fi
}

configure_git_safe_directory() {
  local workspace="${AGENT_WORKSPACE:-}"
  if [[ -z "${workspace}" ]]; then
    return
  fi

  if ! gosu "${AGENT_USER}" git config --global --get-all safe.directory 2>/dev/null | grep -Fx -- "${workspace}" >/dev/null; then
    gosu "${AGENT_USER}" git config --global --add safe.directory "${workspace}" >/dev/null 2>&1 || true
  fi
}

run_as_agent() {
  if [[ "$(id -u)" == "0" ]]; then
    gosu "${AGENT_USER}" "$@"
  else
    "$@"
  fi
}

configure_github_cli_git() {
  if [[ -z "${GH_TOKEN:-}" && -z "${GITHUB_TOKEN:-}" ]]; then
    return
  fi

  if ! command -v gh >/dev/null 2>&1; then
    echo "agent: warning: GH_TOKEN/GITHUB_TOKEN is set but gh is not installed; git push may require login" >&2
    return
  fi

  local host="${GH_HOST:-github.com}"
  if ! GH_PROMPT_DISABLED=1 run_as_agent gh auth setup-git --hostname "${host}" --force >/dev/null 2>&1; then
    echo "agent: warning: could not configure gh as git credential helper for ${host}" >&2
  fi
}

if [[ "$(id -u)" == "0" ]]; then
  mkdir -p "${AGENT_HOME}"
  chown "${AGENT_USER}:${AGENT_USER}" "${AGENT_HOME}" >/dev/null 2>&1 || true
  prepare_writable_dir "${AGENT_UV_DATA_ROOT:-}"
  configure_git_safe_directory
  configure_github_cli_git

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

configure_github_cli_git

exec "$@"
