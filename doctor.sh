#!/usr/bin/env bash
# Check the CLI tools the aws-chatbot apply needs and show how to install the missing ones.
#
# The apply runs helper scripts through Terraform `local-exec` provisioners, so
# `terraform`, `python3`, and the AWS CLI must be on PATH before the first
# `terraform apply`. Run this from the repository root:
#
#   ./doctor.sh             report the required tools
#   ./doctor.sh --optional  also report just and Docker (advisory)
#   ./doctor.sh --install   install the missing tools (add --optional for just and Docker)
#
# Stdlib only: bash and coreutils, so it runs before anything else is installed.
set -euo pipefail

# Minimums from the README prerequisites.
readonly TERRAFORM_MIN="1.10"
readonly PYTHON_MIN="3.10"
readonly AWS_MIN="2.0"

PLATFORM=""
INSTALL=false
OPTIONAL=false
STATUS=0

usage() {
  cat <<'USAGE'
Usage: ./doctor.sh [--install] [--optional]

  --install   Run the install command for each missing tool.
  --optional  Also check just and Docker. Reported, never required.

Checks terraform, python3, and the AWS CLI, the tools the apply needs on PATH.
USAGE
}

parse_args() {
  for arg in "$@"; do
    case "$arg" in
      --install) INSTALL=true ;;
      --optional) OPTIONAL=true ;;
      -h | --help)
        usage
        exit 0
        ;;
      *)
        echo "Unknown argument: $arg" >&2
        usage >&2
        exit 2
        ;;
    esac
  done
}

detect_platform() {
  if [[ -n "${DOCTOR_PLATFORM:-}" ]]; then
    PLATFORM="$DOCTOR_PLATFORM"
    return
  fi
  case "$(uname -s)" in
    Darwin)
      PLATFORM="macos"
      return
      ;;
    Linux) ;;
    *)
      PLATFORM="unknown"
      return
      ;;
  esac
  local os_id os_like
  os_id="$(sed -n 's/^ID=//p' /etc/os-release 2>/dev/null | tr -d '"' || true)"
  os_like="$(sed -n 's/^ID_LIKE=//p' /etc/os-release 2>/dev/null | tr -d '"' || true)"
  case "${os_id} ${os_like}" in
    *debian* | *ubuntu*) PLATFORM="debian" ;;
    *fedora* | *rhel* | *centos*) PLATFORM="fedora" ;;
    *) PLATFORM="unknown" ;;
  esac
}

# Print the first dotted version number found on stdin.
first_version() {
  grep -oE '[0-9]+(\.[0-9]+)+' | sed -n '1p'
}

# Return success when $1 (major.minor...) is at or above $2.
version_ge() {
  local have="$1" want="$2"
  local h_major h_minor w_major w_minor
  IFS=. read -r h_major h_minor _ <<<"$have"
  IFS=. read -r w_major w_minor _ <<<"$want"
  h_minor="${h_minor:-0}"
  w_minor="${w_minor:-0}"
  if ((h_major != w_major)); then
    ((h_major > w_major))
  else
    ((h_minor >= w_minor))
  fi
}

# Echo the install command for a tool on the detected platform, or return 1.
install_cmd() {
  case "${PLATFORM}:$1" in
    macos:terraform) echo "brew install hashicorp/tap/terraform" ;;
    macos:python3) echo "brew install python" ;;
    macos:aws) echo "brew install awscli" ;;
    macos:just) echo "brew install just" ;;
    macos:docker) echo "brew install --cask docker" ;;
    debian:python3) echo "sudo apt-get install -y python3" ;;
    debian:just) echo "sudo apt-get install -y just" ;;
    debian:docker) echo "sudo apt-get install -y docker.io" ;;
    fedora:python3) echo "sudo dnf install -y python3" ;;
    fedora:just) echo "sudo dnf install -y just" ;;
    fedora:docker) echo "sudo dnf install -y docker" ;;
    *) return 1 ;;
  esac
}

# Echo the install documentation link for a tool, or return 1.
install_link() {
  case "$1" in
    terraform) echo "https://developer.hashicorp.com/terraform/install" ;;
    aws) echo "https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html" ;;
    *) return 1 ;;
  esac
}

report_hint() {
  local tool="$1" cmd link
  cmd="$(install_cmd "$tool")" || cmd=""
  link="$(install_link "$tool")" || link=""
  if [[ -n "$cmd" ]]; then
    printf '          install: %s\n' "$cmd"
    if [[ "$INSTALL" == true ]]; then
      printf '          running: %s\n' "$cmd"
      if ! eval "$cmd"; then
        printf '          failed: %s\n' "$cmd" >&2
      fi
    fi
  elif [[ -n "$link" ]]; then
    printf '          install: %s\n' "$link"
  fi
}

check_required() {
  local tool="$1" min="$2"
  shift 2
  if ! command -v "$tool" >/dev/null 2>&1; then
    printf '[missing]  %s\n' "$tool"
    report_hint "$tool"
    STATUS=1
    return
  fi
  local have
  have="$("$tool" "$@" 2>&1 | first_version)" || have=""
  if [[ -z "$have" ]]; then
    printf '[unknown]  %s (version command failed or printed no version)\n' "$tool"
    report_hint "$tool"
    STATUS=1
    return
  fi
  if version_ge "$have" "$min"; then
    printf '[ok]       %s %s\n' "$tool" "$have"
  else
    printf '[outdated] %s %s (need %s or later)\n' "$tool" "$have" "$min"
    report_hint "$tool"
    STATUS=1
  fi
}

check_optional() {
  local tool="$1"
  shift
  if command -v "$tool" >/dev/null 2>&1; then
    local have
    have="$("$tool" "$@" 2>&1 | first_version)" || have=""
    printf '[ok]       %s %s (optional)\n' "$tool" "${have:-unknown}"
  else
    printf '[missing]  %s (optional)\n' "$tool"
    report_hint "$tool"
  fi
}

main() {
  parse_args "$@"
  detect_platform
  printf 'Checking required tools (platform: %s)\n\n' "$PLATFORM"
  check_required terraform "$TERRAFORM_MIN" version
  check_required python3 "$PYTHON_MIN" --version
  check_required aws "$AWS_MIN" --version

  if [[ "$OPTIONAL" == true ]]; then
    printf '\nOptional tools\n\n'
    check_optional just --version
    check_optional docker --version
  fi

  printf '\n'
  if [[ "$STATUS" -eq 0 ]]; then
    echo "All required tools are present."
  else
    echo "Some tools are missing or outdated. Install them, then re-run ./doctor.sh." >&2
  fi
  exit "$STATUS"
}

main "$@"
