#!/bin/bash
# Kage Installation Script for Linux/macOS
# Usage: ./scripts/install.sh [--dev]

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Kage ASCII Banner
echo -e "${CYAN}"
cat << 'EOF'
    ██╗  ██╗ █████╗  ██████╗ ███████╗
    ██║ ██╔╝██╔══██╗██╔════╝ ██╔════╝
    █████╔╝ ███████║██║  ███╗█████╗  
    ██╔═██╗ ██╔══██║██║   ██║██╔══╝  
    ██║  ██╗██║  ██║╚██████╔╝███████╗
    ╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝ ╚══════╝
    AI-Powered Penetration Testing Assistant
EOF
echo -e "${NC}"

# Configuration
INSTALL_DIR="$HOME/.local/share/kage"
VENV_DIR="$INSTALL_DIR/venv"
BIN_DIR="$HOME/.local/bin"
DEV_MODE=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --dev)
            DEV_MODE=true
            shift
            ;;
        --help|-h)
            echo "Usage: ./install.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --dev     Install with development dependencies"
            echo "  --help    Show this help message"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

echo -e "${CYAN}[*] Starting Kage installation...${NC}"

# Check Python version
check_python() {
    echo -e "${YELLOW}[1/6] Checking Python version...${NC}"
    
    if command -v python3 &> /dev/null; then
        PYTHON_CMD="python3"
    elif command -v python &> /dev/null; then
        PYTHON_CMD="python"
    else
        echo -e "${RED}[!] Python not found. Please install Python 3.10 or higher.${NC}"
        exit 1
    fi
    
    PYTHON_VERSION=$($PYTHON_CMD -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    REQUIRED_VERSION="3.10"
    
    if [ "$(printf '%s\n' "$REQUIRED_VERSION" "$PYTHON_VERSION" | sort -V | head -n1)" != "$REQUIRED_VERSION" ]; then
        echo -e "${RED}[!] Python $REQUIRED_VERSION+ required, found $PYTHON_VERSION${NC}"
        exit 1
    fi
    
    echo -e "${GREEN}[✓] Python $PYTHON_VERSION found${NC}"
}

# Check and install system dependencies
check_dependencies() {
    echo -e "${YELLOW}[2/6] Checking system dependencies...${NC}"
    
    MISSING_DEPS=()
    
    # Check for pip
    if ! $PYTHON_CMD -m pip --version &> /dev/null; then
        MISSING_DEPS+=("python3-pip")
    fi
    
    # Check for venv
    if ! $PYTHON_CMD -c "import venv" &> /dev/null; then
        MISSING_DEPS+=("python3-venv")
    fi
    
    # Check for git (for development)
    if ! command -v git &> /dev/null; then
        MISSING_DEPS+=("git")
    fi
    
    if [ ${#MISSING_DEPS[@]} -gt 0 ]; then
        echo -e "${YELLOW}[!] Missing dependencies: ${MISSING_DEPS[*]}${NC}"
        echo -e "${YELLOW}[*] Attempting to install...${NC}"
        
        if command -v apt-get &> /dev/null; then
            sudo apt-get update && sudo apt-get install -y "${MISSING_DEPS[@]}"
        elif command -v dnf &> /dev/null; then
            sudo dnf install -y "${MISSING_DEPS[@]}"
        elif command -v pacman &> /dev/null; then
            sudo pacman -S --noconfirm "${MISSING_DEPS[@]}"
        elif command -v brew &> /dev/null; then
            brew install "${MISSING_DEPS[@]}"
        else
            echo -e "${RED}[!] Could not auto-install dependencies.${NC}"
            echo -e "${RED}    Please install manually: ${MISSING_DEPS[*]}${NC}"
            exit 1
        fi
    fi
    
    echo -e "${GREEN}[✓] All dependencies satisfied${NC}"
}

# Create installation directory and virtual environment
setup_venv() {
    echo -e "${YELLOW}[3/6] Setting up virtual environment...${NC}"
    
    # Create directories
    mkdir -p "$INSTALL_DIR"
    mkdir -p "$BIN_DIR"
    
    # Create virtual environment
    if [ -d "$VENV_DIR" ]; then
        echo -e "${YELLOW}[*] Removing existing virtual environment...${NC}"
        rm -rf "$VENV_DIR"
    fi
    
    $PYTHON_CMD -m venv "$VENV_DIR"
    source "$VENV_DIR/bin/activate"
    
    # Upgrade pip
    pip install --upgrade pip wheel setuptools > /dev/null 2>&1
    
    echo -e "${GREEN}[✓] Virtual environment created${NC}"
}

# Install Kage
install_kage() {
    echo -e "${YELLOW}[4/6] Installing Kage...${NC}"
    
    # Get the script directory (where install.sh is located)
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    KAGE_ROOT="$(dirname "$SCRIPT_DIR")"
    
    # Activate venv
    source "$VENV_DIR/bin/activate"
    
    # Install kage
    if [ "$DEV_MODE" = true ]; then
        echo -e "${CYAN}[*] Installing in development mode...${NC}"
        pip install -e "$KAGE_ROOT[dev]"
    else
        pip install -e "$KAGE_ROOT"
    fi
    
    echo -e "${GREEN}[✓] Kage installed successfully${NC}"
}

# Create launcher script
create_launcher() {
    echo -e "${YELLOW}[5/6] Creating launcher...${NC}"
    
    # Create the launcher script
    cat > "$BIN_DIR/kage" << EOF
#!/bin/bash
# Kage launcher - auto-generated
source "$VENV_DIR/bin/activate"
exec python -m kage "\$@"
EOF
    
    chmod +x "$BIN_DIR/kage"
    
    echo -e "${GREEN}[✓] Launcher created at $BIN_DIR/kage${NC}"
}

# Setup PATH
setup_path() {
    echo -e "${YELLOW}[6/6] Configuring PATH...${NC}"
    
    # Check if BIN_DIR is in PATH
    if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
        # Detect shell and add to appropriate rc file
        SHELL_NAME=$(basename "$SHELL")
        
        case $SHELL_NAME in
            bash)
                RC_FILE="$HOME/.bashrc"
                ;;
            zsh)
                RC_FILE="$HOME/.zshrc"
                ;;
            fish)
                RC_FILE="$HOME/.config/fish/config.fish"
                ;;
            *)
                RC_FILE="$HOME/.profile"
                ;;
        esac
        
        # Add to rc file if not already there
        if ! grep -q "export PATH=\"$BIN_DIR:\$PATH\"" "$RC_FILE" 2>/dev/null; then
            echo "" >> "$RC_FILE"
            echo "# Kage - AI Penetration Testing Assistant" >> "$RC_FILE"
            echo "export PATH=\"$BIN_DIR:\$PATH\"" >> "$RC_FILE"
            echo -e "${YELLOW}[*] Added $BIN_DIR to PATH in $RC_FILE${NC}"
        fi
        
        export PATH="$BIN_DIR:$PATH"
    fi
    
    echo -e "${GREEN}[✓] PATH configured${NC}"
}

# Main installation
main() {
    check_python
    check_dependencies
    setup_venv
    install_kage
    create_launcher
    setup_path
    
    echo ""
    echo -e "${GREEN}════════════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}  Kage installed successfully!${NC}"
    echo -e "${GREEN}════════════════════════════════════════════════════════════${NC}"
    echo ""
    echo -e "${CYAN}  To get started:${NC}"
    echo -e "    ${YELLOW}1.${NC} Restart your terminal or run: ${CYAN}source ~/.bashrc${NC}"
    echo -e "    ${YELLOW}2.${NC} Run setup wizard: ${CYAN}kage setup${NC}"
    echo -e "    ${YELLOW}3.${NC} Start hacking: ${CYAN}kage chat${NC}"
    echo ""
    echo -e "${CYAN}  For autonomous mode:${NC}"
    echo -e "    ${CYAN}kage hack${NC} - Full autonomous penetration testing"
    echo ""
    echo -e "${RED}  ⚠ For authorized security testing only.${NC}"
    echo ""
}

main
