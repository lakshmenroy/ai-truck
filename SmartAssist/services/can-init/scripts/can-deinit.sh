#!/bin/bash
# SmartAssist CAN Bus De-initialization Script
# Brings down can0 interface cleanly on shutdown
#
# Usage: ./can-deinit.sh
# Exit codes: 0 = success, 1 = failure

set -e

CAN_INTERFACE="can0"

echo "[CAN Deinit] Starting CAN bus de-initialization..."

# Check if CAN interface exists
if ! ip link show "$CAN_INTERFACE" &>/dev/null; then
    echo "[CAN Deinit] WARNING: CAN interface $CAN_INTERFACE not found"
    exit 0  # Not an error - interface might not exist
fi

# Check if already DOWN
if ip link show "$CAN_INTERFACE" | grep -q "state DOWN"; then
    echo "[CAN Deinit] INFO: $CAN_INTERFACE is already DOWN"
    exit 0
fi

# Bring interface DOWN
echo "[CAN Deinit] Bringing down $CAN_INTERFACE..."
ip link set "$CAN_INTERFACE" down

# Verify
if ip link show "$CAN_INTERFACE" | grep -q "state DOWN"; then
    echo "[CAN Deinit] SUCCESS: $CAN_INTERFACE brought down cleanly"
    exit 0
else
    echo "[CAN Deinit] WARNING: Failed to bring down $CAN_INTERFACE"
    exit 1
fi
