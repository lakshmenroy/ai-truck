#!/bin/bash
# SmartAssist CAN Bus Initialization Script
# Initializes can0 interface at 250kbps for vehicle CAN communication
#
# Usage: ./can-init.sh
# Exit codes: 0 = success, 1 = failure

set -e

CAN_INTERFACE="can0"
BITRATE="250000"
TXQUEUELEN="1000"
RESTART_MS="100"

echo "[CAN Init] Starting CAN bus initialization..."

# Check if CAN interface exists
if ! ip link show "$CAN_INTERFACE" &>/dev/null; then
    echo "[CAN Init] ERROR: CAN interface $CAN_INTERFACE not found!"
    exit 1
fi

# Check if already UP
if ip link show "$CAN_INTERFACE" | grep -q "state UP"; then
    echo "[CAN Init] WARNING: $CAN_INTERFACE is already UP"
    echo "[CAN Init] Bringing down for reconfiguration..."
    ip link set "$CAN_INTERFACE" down
fi

# Configure CAN interface
echo "[CAN Init] Configuring $CAN_INTERFACE..."
ip link set "$CAN_INTERFACE" type can bitrate "$BITRATE"
ip link set "$CAN_INTERFACE" txqueuelen "$TXQUEUELEN"
ip link set "$CAN_INTERFACE" restart-ms "$RESTART_MS"

# Bring interface UP
echo "[CAN Init] Bringing up $CAN_INTERFACE..."
ip link set "$CAN_INTERFACE" up

# Verify configuration
if ip link show "$CAN_INTERFACE" | grep -q "state UP"; then
    echo "[CAN Init] SUCCESS: $CAN_INTERFACE initialized"
    echo "[CAN Init] Configuration:"
    echo "  - Interface: $CAN_INTERFACE"
    echo "  - Bitrate: $BITRATE bps"
    echo "  - TX Queue Length: $TXQUEUELEN"
    echo "  - Auto-restart: $RESTART_MS ms"
    ip -details link show "$CAN_INTERFACE"
    exit 0
else
    echo "[CAN Init] ERROR: Failed to bring up $CAN_INTERFACE"
    exit 1
fi
