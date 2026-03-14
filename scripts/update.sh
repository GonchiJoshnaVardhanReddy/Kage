#!/bin/bash
# Kage Update Script for Linux/macOS
# Usage: ./scripts/update.sh [--dev]

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

DEV_MODE=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dev)
            DEV_MODE=true
            shift
            ;;
        --help|-h)
            echo "Usage: ./scripts/update.sh [--dev]"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

echo -e "${CYAN}[*] Updating Kage...${NC}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KAGE_ROOT="$(dirname "$SCRIPT_DIR")"

if [[ -d "$HOME/.local/share/kage/venv" ]]; then
    VENV_PY="$HOME/.local/share/kage/venv/bin/python"
elif [[ -n "${VIRTUAL_ENV:-}" ]]; then
    VENV_PY="$VIRTUAL_ENV/bin/python"
else
    VENV_PY="python3"
fi

if [[ "$DEV_MODE" == true ]]; then
    "$VENV_PY" -m pip install -e "$KAGE_ROOT[dev]"
else
    "$VENV_PY" -m pip install -e "$KAGE_ROOT"
fi

echo -e "${GREEN}[✓] Kage update complete${NC}"
echo -e "${CYAN}Run 'kage --version' to verify.${NC}"
