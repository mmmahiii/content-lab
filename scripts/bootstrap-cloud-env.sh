#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export DEBIAN_FRONTEND=noninteractive
export PATH="$HOME/.local/bin:$PATH"

if [[ "$(id -u)" -eq 0 ]]; then
  SUDO=""
else
  SUDO="sudo"
fi

log() {
  echo "[cloud-bootstrap] $*"
}

apt_has_package() {
  apt-cache show "$1" >/dev/null 2>&1
}

install_apt_packages() {
  local packages=("$@")
  if ((${#packages[@]} == 0)); then
    return
  fi
  log "Installing apt packages: ${packages[*]}"
  ${SUDO} apt-get update
  ${SUDO} apt-get install -y "${packages[@]}"
}

ensure_base_packages() {
  local wanted=(
    ca-certificates
    curl
    fuse-overlayfs
    iptables
    pipx
    software-properties-common
  )
  local missing=()
  local pkg
  for pkg in "${wanted[@]}"; do
    if ! dpkg -s "${pkg}" >/dev/null 2>&1; then
      missing+=("${pkg}")
    fi
  done

  local compose_pkg=""
  if apt_has_package docker-compose-v2; then
    compose_pkg="docker-compose-v2"
  elif apt_has_package docker-compose-plugin; then
    compose_pkg="docker-compose-plugin"
  fi

  if ! dpkg -s docker.io >/dev/null 2>&1; then
    missing+=("docker.io")
  fi
  if [[ -n "${compose_pkg}" ]] && ! dpkg -s "${compose_pkg}" >/dev/null 2>&1; then
    missing+=("${compose_pkg}")
  fi

  install_apt_packages "${missing[@]}"
}

ensure_python311() {
  if command -v python3.11 >/dev/null 2>&1; then
    return
  fi

  log "Installing Python 3.11 from deadsnakes PPA"
  ${SUDO} add-apt-repository -y ppa:deadsnakes/ppa
  ${SUDO} apt-get update

  local py_packages=(
    python3.11
    python3.11-dev
    python3.11-distutils
    python3.11-venv
  )
  ${SUDO} apt-get install -y "${py_packages[@]}"
}

ensure_poetry() {
  if [[ -x "$HOME/.local/bin/poetry" ]] || command -v poetry >/dev/null 2>&1; then
    return
  fi

  if ! command -v pipx >/dev/null 2>&1; then
    install_apt_packages pipx
  fi

  log "Installing Poetry via pipx"
  pipx install --python python3.11 poetry
  pipx ensurepath || true
}

ensure_shell_profile_defaults() {
  local marker="# >>> content-lab cloud bootstrap >>>"
  local snippet
  read -r -d '' snippet <<'EOF' || true
# >>> content-lab cloud bootstrap >>>
export PATH="$HOME/.local/bin:$PATH"
export NVM_DIR="$HOME/.nvm"
if [ -s "$NVM_DIR/nvm.sh" ]; then
  . "$NVM_DIR/nvm.sh"
  nvm use --silent default >/dev/null 2>&1 || true
fi
# <<< content-lab cloud bootstrap <<<
EOF

  local profile
  for profile in "$HOME/.bashrc" "$HOME/.profile"; do
    touch "$profile"
    if ! rg -q "content-lab cloud bootstrap" "$profile"; then
      printf "\n%s\n" "$snippet" >> "$profile"
    fi
  done
}

configure_default_node_shims() {
  mkdir -p "$HOME/.local/bin"
  local node_bin_dir
  node_bin_dir="$(dirname "$(command -v node)")"

  ln -sf "${node_bin_dir}/node" "$HOME/.local/bin/node"
  if [[ -x "${node_bin_dir}/npm" ]]; then
    ln -sf "${node_bin_dir}/npm" "$HOME/.local/bin/npm"
  fi
  if [[ -x "${node_bin_dir}/npx" ]]; then
    ln -sf "${node_bin_dir}/npx" "$HOME/.local/bin/npx"
  fi
  if command -v pnpm >/dev/null 2>&1; then
    ln -sf "$(command -v pnpm)" "$HOME/.local/bin/pnpm"
  fi
}

ensure_node24_with_nvm() {
  export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
  if [[ ! -s "${NVM_DIR}/nvm.sh" ]]; then
    log "Installing nvm"
    curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh | bash
  fi

  # shellcheck source=/dev/null
  . "${NVM_DIR}/nvm.sh"

  log "Ensuring Node.js 24 is installed and default"
  nvm install 24
  nvm alias default 24
  nvm use 24

  corepack enable
  corepack prepare pnpm@9 --activate
  configure_default_node_shims
  ensure_shell_profile_defaults
}

configure_nested_docker() {
  if [[ -x /usr/sbin/iptables-legacy ]]; then
    ${SUDO} update-alternatives --set iptables /usr/sbin/iptables-legacy || true
  fi
  if [[ -x /usr/sbin/ip6tables-legacy ]]; then
    ${SUDO} update-alternatives --set ip6tables /usr/sbin/ip6tables-legacy || true
  fi

  local daemon_pids=()
  mapfile -t daemon_pids < <(pgrep -x dockerd || true)
  if ((${#daemon_pids[@]} > 0)); then
    log "Stopping existing dockerd PID(s): ${daemon_pids[*]}"
    ${SUDO} kill "${daemon_pids[@]}" || true

    local wait_kill=0
    while pgrep -x dockerd >/dev/null 2>&1; do
      sleep 1
      wait_kill=$((wait_kill + 1))
      if ((wait_kill >= 15)); then
        mapfile -t daemon_pids < <(pgrep -x dockerd || true)
        if ((${#daemon_pids[@]} > 0)); then
          log "Force-stopping dockerd PID(s): ${daemon_pids[*]}"
          ${SUDO} kill -9 "${daemon_pids[@]}" || true
        fi
        break
      fi
    done
  fi

  if [[ -f /var/run/docker.pid ]]; then
    local stale_pid=""
    stale_pid="$(awk 'NR==1 {print $1}' /var/run/docker.pid 2>/dev/null || true)"
    if [[ -n "${stale_pid}" ]] && ! ps -p "${stale_pid}" >/dev/null 2>&1; then
      log "Removing stale /var/run/docker.pid for PID ${stale_pid}"
      ${SUDO} rm -f /var/run/docker.pid
    fi
  fi

  log "Starting dockerd with fuse-overlayfs"
  ${SUDO} nohup dockerd --storage-driver=fuse-overlayfs > /tmp/dockerd.log 2>&1 &

  local waited=0
  until ${SUDO} docker info >/dev/null 2>&1; do
    sleep 1
    waited=$((waited + 1))
    if ((waited >= 30)); then
      log "Docker daemon failed to start within timeout"
      return 1
    fi
  done

  ${SUDO} usermod -aG docker "${USER}" || true
  if [[ -S /var/run/docker.sock ]]; then
    ${SUDO} chmod 666 /var/run/docker.sock || true
  fi

  local driver
  driver="$(${SUDO} docker info --format '{{.Driver}}' 2>/dev/null || true)"
  if [[ "${driver}" != "fuse-overlayfs" ]]; then
    log "Warning: docker storage driver is '${driver}', expected 'fuse-overlayfs'."
  fi
}

ensure_repo_env() {
  if [[ ! -f "${REPO_ROOT}/.env" ]]; then
    log "Creating .env from infra/.env.example"
    cp "${REPO_ROOT}/infra/.env.example" "${REPO_ROOT}/.env"
  fi
}

main() {
  ensure_base_packages
  ensure_python311
  ensure_poetry
  configure_nested_docker
  ensure_node24_with_nvm
  ensure_repo_env

  log "Running scaffold compatibility layout setup"
  bash "${REPO_ROOT}/scripts/ensure-scaffold-compat.sh"

  log "Installing JavaScript workspace dependencies"
  pnpm install

  log "Cloud bootstrap complete"
}

main "$@"
