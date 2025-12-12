# GPIO Export Service

**Purpose:** Export GPIO pins to userspace for IGNITION signal monitoring

---

## Overview

This service exports the IGNITION GPIO pin (PH.01) to userspace at boot time, making it accessible to the GPIO Monitor service. This is required for the vehicle's IGNITION signal to be monitored by the SmartAssist system.

---

## What It Does

1. Runs at system boot (after sysinit.target)
2. Verifies GPIO pin PH.01 (IGNITION) is accessible
3. Remains active after execution (RemainAfterExit=yes)
4. Required by GPIO Monitor service

---

## Installation

```bash
# Copy service file
sudo cp smartassist-gpio-export.service /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable service (start at boot)
sudo systemctl enable smartassist-gpio-export

# Start service now
sudo systemctl start smartassist-gpio-export
```

---

## Testing

```bash
# Check service status
systemctl status smartassist-gpio-export

# Verify GPIO is accessible
gpioget $(gpiofind PH.01)

# Should return 0 or 1 (GPIO state)
# If error, GPIO export failed
```

---

## Dependencies

**Requires:**
- `sysinit.target` - System initialization

**Required by:**
- `smartassist-gpio-monitor.service` - GPIO monitoring

---

## Troubleshooting

### Service fails to start

**Problem:** GPIO pin not found

**Solution:**
```bash
# List available GPIO pins
gpiodetect

# Find IGNITION pin
gpiofind PH.01

# If not found, check hardware documentation
# Pin name may differ on your platform
```

### Service starts but GPIO not accessible

**Problem:** Permissions issue

**Solution:**
```bash
# Check if libgpiod is installed
sudo apt install libgpiod2 gpiod

# Verify user has GPIO access
sudo usermod -aG gpio $USER
```

---

## Hardware Details

**GPIO Pin:** PH.01  
**Purpose:** IGNITION signal from vehicle  
**Type:** Digital input (HIGH when ignition ON, LOW when OFF)  
**Voltage:** 3.3V logic level

---

## Notes

- This is a **oneshot** service (runs once at boot)
- **RemainAfterExit=yes** keeps service active after script completes
- Required before any GPIO monitoring can occur
- Does not continuously run - just enables GPIO access

---

## Related Services

- **smartassist-gpio-monitor.service** - Monitors IGNITION state
- **smartassist-gpio-monitor.timer** - Triggers monitoring every 5s
