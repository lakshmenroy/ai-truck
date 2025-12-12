# CAN Init Service

**Purpose:** Initialize CAN bus interface (can0) at 250kbps for vehicle communication

---

## Overview

This service initializes the CAN0 interface at system boot, configuring it for 250kbps communication with the vehicle CAN bus. It's a foundational service required by both the CAN server and time sync services.

---

## What It Does

### **Initialization (can-init.sh):**
1. Checks if can0 interface exists
2. Brings down interface if already UP
3. Configures:
   - Bitrate: 250000 bps (250 kbps)
   - TX queue length: 1000
   - Auto-restart: 100ms (on bus-off)
4. Brings interface UP
5. Verifies configuration

### **De-initialization (can-deinit.sh):**
1. Cleanly brings down can0 on shutdown
2. Ensures proper cleanup

---

## Installation

```bash
# Make scripts executable
chmod +x services/can-init/scripts/*.sh

# Copy service files
sudo cp services/can-init/smartassist-can-init.service /etc/systemd/system/
sudo cp services/can-init/smartassist-can-deinit.service /etc/systemd/system/

# Copy scripts to system location
sudo mkdir -p /opt/smartassist/services/can-init/scripts
sudo cp services/can-init/scripts/*.sh /opt/smartassist/services/can-init/scripts/
sudo chmod +x /opt/smartassist/services/can-init/scripts/*.sh

# Reload systemd
sudo systemctl daemon-reload

# Enable services
sudo systemctl enable smartassist-can-init
sudo systemctl enable smartassist-can-deinit

# Start init service now
sudo systemctl start smartassist-can-init
```

---

## Testing

```bash
# Check service status
systemctl status smartassist-can-init

# Verify CAN interface is UP
ip link show can0
# Should show: state UP, bitrate 250000

# Monitor CAN messages
candump can0
# Should show live CAN traffic from vehicle

# Check detailed stats
ip -details -statistics link show can0
```

---

## Dependencies

### **Init Service:**
**Requires:**
- `network.target` - Network subsystem

**Required by:**
- `smartassist-can-server.service` - CAN message server
- `smartassist-time-sync.service` - Time synchronization

### **Deinit Service:**
**Runs before:**
- `shutdown.target` - System shutdown
- `reboot.target` - System reboot
- `halt.target` - System halt

---

## Configuration

Edit scripts to change CAN parameters:

```bash
# In can-init.sh
CAN_INTERFACE="can0"      # CAN interface name
BITRATE="250000"          # 250 kbps (vehicle standard)
TXQUEUELEN="1000"         # TX queue size
RESTART_MS="100"          # Auto-restart delay (ms)
```

**Common bitrates:**
- 125000 (125 kbps) - Low-speed CAN
- 250000 (250 kbps) - Standard vehicle CAN
- 500000 (500 kbps) - High-speed CAN
- 1000000 (1 Mbps) - CAN-FD

---

## Troubleshooting

### Service fails: "CAN interface not found"

**Problem:** Hardware CAN interface not detected

**Solution:**
```bash
# Check if CAN hardware exists
lsmod | grep can
lsmod | grep mttcan  # For Jetson Orin

# Load CAN drivers
sudo modprobe can
sudo modprobe can_raw
sudo modprobe mttcan  # For Jetson Orin

# Verify interface exists
ip link show can0
```

### Service fails: "Cannot bring up interface"

**Problem:** Permission or hardware issue

**Solution:**
```bash
# Check dmesg for errors
dmesg | grep -i can

# Try manual init
sudo ip link set can0 type can bitrate 250000
sudo ip link set can0 up

# Check for hardware errors
ip -details link show can0
```

### No CAN messages visible (candump empty)

**Problem:** No CAN traffic or wrong bitrate

**Solution:**
```bash
# Verify bitrate matches vehicle (usually 250k or 500k)
ip -details link show can0 | grep bitrate

# Check CAN bus stats
ip -statistics link show can0
# Look for RX/TX packets, errors

# Check physical connection
# - Verify CAN-H and CAN-L wiring
# - Check 120Ω termination resistor
# - Verify vehicle power is ON
```

### Interface keeps going to BUS-OFF state

**Problem:** Communication errors or wrong bitrate

**Solution:**
```bash
# Check error counters
ip -details -statistics link show can0

# Increase restart time
# Edit can-init.sh: RESTART_MS="500"

# Verify termination resistor (120Ω)
# Check wiring quality
```

---

## Hardware Details

**Interface:** can0 (Jetson built-in CAN)  
**Bitrate:** 250000 bps (250 kbps)  
**Topology:** Vehicle CAN bus (ISO 11898)  
**Termination:** 120Ω resistor required at both ends  
**Connector:** Varies by vehicle (typically DB9 or bare wire)

---

## Notes

- This is a **oneshot** service (runs once at boot)
- **RemainAfterExit=yes** keeps service marked as active
- Deinit service runs automatically on shutdown
- CAN server will fail if this service is not running
- Monitor with: `journalctl -u smartassist-can-init -f`

---

## Related Services

- **smartassist-can-server.service** - Requires this service
- **smartassist-time-sync.service** - Requires this service
- **smartassist-pipeline.service** - Indirectly requires (via CAN server)
