#!/bin/bash
# Kage Uninstall Script for Linux/macOS
# Usage: ./scripts/uninstall.sh [--yes] [--dry-run] [--skip-pip]

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

DRY_RUN=false
YES=false
SKIP_PIP=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --yes|-y)
            YES=true
            shift
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --skip-pip)
            SKIP_PIP=true
            shift
            ;;
        --help|-h)
            echo "Usage: ./scripts/uninstall.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --yes       Non-interactive mode (don't prompt)"
            echo "  --dry-run   Show actions without deleting anything"
            echo "  --skip-pip  Skip pip uninstall"
            echo "  --help      Show this help message"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

run_remove_path() {
    local target="$1"
    if [[ ! -e "$target" ]]; then
        echo -e "${CYAN}[*] Not found:${NC} $target"
        return
    fi

    if [[ "$DRY_RUN" == true ]]; then
        echo -e "${YELLOW}[dry-run] Would remove:${NC} $target"
        return
    fi

    rm -rf "$target"
    echo -e "${GREEN}[✓] Removed:${NC} $target"
}

cleanup_shell_rc_files() {
    local files=(
        "$HOME/.bashrc"
        "$HOME/.zshrc"
        "$HOME/.profile"
    )

    if [[ "$DRY_RUN" == true ]]; then
        echo -e "${YELLOW}[dry-run] Would clean Kage PATH block in shell rc files${NC}"
        return
    fi

    python3 - <<'PY'
from pathlib import Path

files = [Path.home() / ".bashrc", Path.home() / ".zshrc", Path.home() / ".profile"]

for path in files:
    if not path.exists():
        continue

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        continue

    out: list[str] = []
    i = 0
    changed = False
    while i < len(lines):
        line = lines[i]
        if line.strip() == "# Kage - AI Penetration Testing Assistant":
            changed = True
            i += 1
            if i < len(lines) and "export PATH=" in lines[i] and ".local/bin" in lines[i]:
                i += 1
            continue
        out.append(line)
        i += 1

    if changed:
        path.write_text(("\n".join(out) + "\n") if out else "", encoding="utf-8")
        print(f"[✓] Cleaned PATH marker in: {path}")
PY
}

uninstall_pip_package() {
    if [[ "$SKIP_PIP" == true ]]; then
        echo -e "${CYAN}[*] Skipping pip uninstall (--skip-pip).${NC}"
        return
    fi

    if [[ "$DRY_RUN" == true ]]; then
        echo -e "${YELLOW}[dry-run] Would run: pip uninstall -y kage${NC}"
        return
    fi

    local py=""
    if command -v python3 >/dev/null 2>&1; then
        py="python3"
    elif command -v python >/dev/null 2>&1; then
        py="python"
    fi

    if [[ -n "$py" ]]; then
        "$py" -m pip uninstall -y kage >/dev/null 2>&1 || true
        echo -e "${GREEN}[✓] pip uninstall attempted${NC}"
    else
        echo -e "${YELLOW}[!] Python not found; skipped pip uninstall${NC}"
    fi
}

echo -e "${CYAN}[*] Kage uninstall starting...${NC}"
echo -e "${YELLOW}This will remove Kage install, config, and data directories.${NC}"

if [[ "$YES" == false && "$DRY_RUN" == false ]]; then
    read -r -p "Proceed? [y/N] " confirm
    if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
        echo -e "${CYAN}[*] Cancelled.${NC}"
        exit 0
    fi
fi

# New + legacy paths
run_remove_path "$HOME/.kage"
run_remove_path "$HOME/.config/kage"
run_remove_path "$HOME/.local/share/kage"
run_remove_path "$HOME/.cache/kage"
run_remove_path "$HOME/.local/bin/kage"

cleanup_shell_rc_files
uninstall_pip_package

echo ""
echo -e "${GREEN}════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  Kage uninstall completed${NC}"
echo -e "${GREEN}════════════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}If you used a custom path, also check:${NC} KAGE_CONFIG_DIR / KAGE_DATA_DIR"
