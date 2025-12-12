#!/bin/bash
# SmartAssist Services Master Installation Script
# Installs all SmartAssist systemd services
#
# Usage: sudo ./install_services.sh
#
# This script:
# 1. Copies all service files to /etc/systemd/system/
# 2. Copies all scripts to /opt/smartassist/
# 3. Sets proper permissions
# 4. Reloads systemd
# 5. Enables services (does not start them)

set -e

# Configuration
SMARTASSIST_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYSTEMD_DIR="/etc/systemd/system"
OPT_DIR="/opt/smartassist"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo -e "${RED}This script must be run as root (use sudo)${NC}"
   exit 1
fi

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}SmartAssist Services Installation${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Create base directories
echo -e "${BLUE}Creating directories...${NC}"
mkdir -p "$OPT_DIR"
mkdir -p "$OPT_DIR/services"
mkdir -p "$OPT_DIR/tools"
mkdir -p /var/lib/smartassist
mkdir -p /var/log/smartassist

# Function to install a service
install_service() {
    local service_dir="$1"
    local service_name="$2"
    
    echo -e "${BLUE}Installing $service_name...${NC}"
    
    # Copy service directory
    if [ -d "$SMARTASSIST_ROOT/services/$service_dir" ]; then
        cp -r "$SMARTASSIST_ROOT/services/$service_dir" "$OPT_DIR/services/"
        
        # Make scripts executable
        if [ -d "$OPT_DIR/services/$service_dir/src" ]; then
            chmod +x "$OPT_DIR/services/$service_dir/src"/*.sh 2>/dev/null || true
            chmod +x "$OPT_DIR/services/$service_dir/src"/*.py 2>/dev/null || true
        fi
        if [ -d "$OPT_DIR/services/$service_dir/scripts" ]; then
            chmod +x "$OPT_DIR/services/$service_dir/scripts"/*.sh 2>/dev/null || true
        fi
        
        # Copy service files to systemd
        cp "$SMARTASSIST_ROOT/services/$service_dir"/*.service "$SYSTEMD_DIR/" 2>/dev/null || true
        cp "$SMARTASSIST_ROOT/services/$service_dir"/*.timer "$SYSTEMD_DIR/" 2>/dev/null || true
        
        echo -e "${GREEN}✓ $service_name installed${NC}"
    else
        echo -e "${YELLOW}⚠ $service_dir directory not found, skipping${NC}"
    fi
}

# Install services
echo ""
echo -e "${BLUE}Installing services...${NC}"
echo ""

install_service "gpio-export" "GPIO Export"
install_service "can-init" "CAN Init/Deinit"
install_service "gpio-monitor" "GPIO Monitor"
install_service "time-sync" "Time Sync"
install_service "can-server" "CAN Server"
install_service "health-monitor" "Health Monitor"

# Install tools
echo ""
echo -e "${BLUE}Installing tools...${NC}"
if [ -d "$SMARTASSIST_ROOT/tools" ]; then
    cp -r "$SMARTASSIST_ROOT/tools"/* "$OPT_DIR/tools/"
    chmod +x "$OPT_DIR/tools"/*.py 2>/dev/null || true
    
    # Copy camera init service file
    if [ -f "$SMARTASSIST_ROOT/tools/smartassist-camera-init.service" ]; then
        cp "$SMARTASSIST_ROOT/tools/smartassist-camera-init.service" "$SYSTEMD_DIR/"
        echo -e "${GREEN}✓ Camera Init service installed${NC}"
    fi
fi

# Install pipeline service file (if exists)
echo ""
echo -e "${BLUE}Installing pipeline service...${NC}"
if [ -f "$SMARTASSIST_ROOT/pipeline/smartassist-pipeline.service" ]; then
    cp "$SMARTASSIST_ROOT/pipeline/smartassist-pipeline.service" "$SYSTEMD_DIR/"
    echo -e "${GREEN}✓ Pipeline service installed${NC}"
else
    echo -e "${YELLOW}⚠ Pipeline service file not found${NC}"
    echo -e "${YELLOW}  Create it at: $SMARTASSIST_ROOT/pipeline/smartassist-pipeline.service${NC}"
fi

# Reload systemd
echo ""
echo -e "${BLUE}Reloading systemd daemon...${NC}"
systemctl daemon-reload
echo -e "${GREEN}✓ Systemd reloaded${NC}"

# Enable services
echo ""
echo -e "${BLUE}Enabling services...${NC}"
echo ""

enable_service() {
    local service="$1"
    if [ -f "$SYSTEMD_DIR/$service" ]; then
        systemctl enable "$service" 2>/dev/null || echo -e "${YELLOW}⚠ Could not enable $service${NC}"
        echo -e "${GREEN}✓ $service enabled${NC}"
    fi
}

# Enable oneshot services
enable_service "smartassist-gpio-export.service"
enable_service "smartassist-can-init.service"
enable_service "smartassist-can-deinit.service"
enable_service "smartassist-camera-init.service"

# Enable daemon services
enable_service "smartassist-can-server.service"
enable_service "smartassist-time-sync.service"
enable_service "smartassist-pipeline.service"

# Enable timer services (NOT the .service, the .timer!)
enable_service "smartassist-gpio-monitor.timer"
enable_service "smartassist-health-monitor.timer"

# Install Python dependencies
echo ""
echo -e "${BLUE}Installing Python dependencies...${NC}"
if [ -f "$SMARTASSIST_ROOT/services/time-sync/requirements.txt" ]; then
    pip3 install -r "$SMARTASSIST_ROOT/services/time-sync/requirements.txt" --break-system-packages || \
    pip3 install -r "$SMARTASSIST_ROOT/services/time-sync/requirements.txt"
    echo -e "${GREEN}✓ Time sync dependencies installed${NC}"
fi

if [ -f "$SMARTASSIST_ROOT/services/can-server/requirements.txt" ]; then
    pip3 install -r "$SMARTASSIST_ROOT/services/can-server/requirements.txt" --break-system-packages || \
    pip3 install -r "$SMARTASSIST_ROOT/services/can-server/requirements.txt"
    echo -e "${GREEN}✓ CAN server dependencies installed${NC}"
fi

# Summary
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Installation Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${BLUE}Installed services:${NC}"
echo "  • smartassist-gpio-export.service"
echo "  • smartassist-can-init.service"
echo "  • smartassist-can-deinit.service"
echo "  • smartassist-camera-init.service"
echo "  • smartassist-can-server.service"
echo "  • smartassist-time-sync.service"
echo "  • smartassist-pipeline.service"
echo "  • smartassist-gpio-monitor.timer"
echo "  • smartassist-health-monitor.timer"
echo ""
echo -e "${BLUE}Next steps:${NC}"
echo ""
echo "1. Review service configurations in /opt/smartassist/services/"
echo "2. Update DBC paths and message names if needed"
echo "3. Start services:"
echo ""
echo "   # Start foundation services"
echo "   sudo systemctl start smartassist-gpio-export"
echo "   sudo systemctl start smartassist-can-init"
echo "   sudo systemctl start smartassist-camera-init"
echo ""
echo "   # Start daemon services"
echo "   sudo systemctl start smartassist-can-server"
echo "   sudo systemctl start smartassist-time-sync"
echo "   sudo systemctl start smartassist-pipeline"
echo ""
echo "   # Start monitoring timers"
echo "   sudo systemctl start smartassist-gpio-monitor.timer"
echo "   sudo systemctl start smartassist-health-monitor.timer"
echo ""
echo "4. Check service status:"
echo "   systemctl status smartassist-*"
echo ""
echo "5. View logs:"
echo "   journalctl -u smartassist-* -f"
echo ""
echo "6. Check health:"
echo "   cat /var/lib/smartassist/service_status.json"
echo ""
echo -e "${GREEN}Installation successful!${NC}"
echo ""
