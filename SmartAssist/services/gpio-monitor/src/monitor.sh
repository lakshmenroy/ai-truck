#!/bin/bash
# SmartAssist GPIO IGNITION Monitor Script
# Monitors IGNITION GPIO signal and triggers graceful shutdown when LOW
#
# Usage: ./monitor.sh
# Runs continuously, checks IGNITION every 5 seconds via timer
#
# Exit codes: 0 = IGNITION ON, 1 = IGNITION OFF (shutdown triggered)

# Configuration
GPIO_PIN="PH.01"                    # IGNITION GPIO pin
LOCK_FILE="/run/lock/smartassist_gpio_monitor.lock"
PIPELINE_PID_FILE="/run/smartassist/pipeline.pid"
PIPELINE_SERVICE="smartassist-pipeline.service"

# Colors for logging
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log() {
    echo "[GPIO Monitor] $1"
    logger -t smartassist-gpio-monitor "$1"
}

log_success() {
    echo -e "${GREEN}[GPIO Monitor] $1${NC}"
    logger -t smartassist-gpio-monitor "$1"
}

log_warning() {
    echo -e "${YELLOW}[GPIO Monitor] WARNING: $1${NC}"
    logger -t smartassist-gpio-monitor "WARNING: $1"
}

log_error() {
    echo -e "${RED}[GPIO Monitor] ERROR: $1${NC}"
    logger -t smartassist-gpio-monitor "ERROR: $1"
}

# Check for lock file (prevent concurrent runs)
if [ -e "$LOCK_FILE" ]; then
    log "Lock file exists, another instance may be running"
    exit 0
fi

# Create lock file
touch "$LOCK_FILE"
trap "rm -f $LOCK_FILE" EXIT

# Get GPIO pin chip and line
GPIO_CHIP=$(gpiofind "$GPIO_PIN" 2>/dev/null | cut -d' ' -f1)
GPIO_LINE=$(gpiofind "$GPIO_PIN" 2>/dev/null | cut -d' ' -f2)

if [ -z "$GPIO_CHIP" ] || [ -z "$GPIO_LINE" ]; then
    log_error "GPIO pin $GPIO_PIN not found!"
    log_error "Run: gpiodetect && gpiofind $GPIO_PIN"
    exit 1
fi

log "Monitoring GPIO: $GPIO_PIN ($GPIO_CHIP $GPIO_LINE)"

# Read GPIO state
GPIO_STATE=$(gpioget "$GPIO_CHIP" "$GPIO_LINE" 2>/dev/null)

if [ $? -ne 0 ]; then
    log_error "Failed to read GPIO state"
    exit 1
fi

log "IGNITION state: $GPIO_STATE (0=OFF, 1=ON)"

# Check IGNITION state
if [ "$GPIO_STATE" == "1" ]; then
    # IGNITION is ON - normal operation
    log_success "IGNITION is ON - system running normally"
    exit 0
else
    # IGNITION is OFF - trigger shutdown
    log_warning "IGNITION is OFF - initiating graceful shutdown!"
    
    # Try to stop pipeline gracefully first
    if systemctl is-active --quiet "$PIPELINE_SERVICE"; then
        log "Stopping pipeline service gracefully..."
        systemctl stop "$PIPELINE_SERVICE" --no-block
        
        # Give pipeline 10 seconds to save data
        sleep 10
    fi
    
    # Check if pipeline stopped
    if systemctl is-active --quiet "$PIPELINE_SERVICE"; then
        log_warning "Pipeline still running after 10s, forcing stop..."
        systemctl kill "$PIPELINE_SERVICE"
    fi
    
    # Trigger system shutdown
    log "Triggering system poweroff..."
    /usr/bin/systemctl poweroff
    
    exit 1
fi
