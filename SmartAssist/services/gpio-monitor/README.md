# GPIO Monitor Service

**Purpose:** Monitor IGNITION GPIO signal and trigger graceful shutdown when vehicle power is disconnected

---

## Overview

This service monitors the vehicle IGNITION signal (GPIO pin PH.01) every 5 seconds. When IGNITION goes LOW (vehicle turned off), it triggers a graceful shutdown sequence:

1. Stop SmartAssist pipeline (gives 10s to save data)
2. Trigger system poweroff
3. Allows time for clean shutdown before hardware watchdog forces power off

This prevents data corruption and ensures logs/videos are saved properly.

---

## What It Does

### **Monitoring Script (monitor.sh):**
1. Reads GPIO pin PH.01 (IGNITION) state
2. If HIGH (1): IGNITION ON → Normal operation, exit 0
3. If LOW (0): IGNITION OFF → Trigger shutdown:
   - Stop `smartassist-pipeline.service` gracefully
   - Wait 10 seconds for data saving
   - Force kill pipeline if still running
   - Execute `systemctl poweroff`

### **Timer:**
- Runs monitoring script every 5 seconds
- Starts 10 seconds after boot
- Continues until shutdown

---

## Installation

```bash
# Make script executable
chmod +x services/gpio-monitor/src/monitor.sh

# Copy files to system locations
sudo mkdir -p /opt/smartassist/services/gpio-monitor/src
sudo cp services/gpio-monitor/src/monitor.sh /opt/smartassist/services/gpio-monitor/src/
sudo chmod +x /opt/smartassist/services/gpio-monitor/src/monitor.sh

sudo cp services/gpio-monitor/smartassist-gpio-monitor.service /etc/systemd/system/
sudo cp services/gpio-monitor/smartassist-gpio-monitor.timer /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable timer (NOT the service directly - timer triggers service)
sudo systemctl enable smartassist-gpio-monitor.timer

# Start timer now
sudo systemctl start smartassist-gpio-monitor.timer
```

---

## Testing

### **Safe Testing (without triggering shutdown):**

```bash
# Check timer status
systemctl status smartassist-gpio-monitor.timer

# List timer schedule
systemctl list-timers smartassist-gpio-monitor.timer

# View logs (should see IGNITION ON messages every 5s)
journalctl -u smartassist-gpio-monitor -f
```

### **Test Shutdown Behavior (CAUTION!):**

⚠️ **WARNING:** This will trigger real shutdown!

```bash
# Temporarily modify script to just log instead of shutdown
sudo nano /opt/smartassist/services/gpio-monitor/src/monitor.sh
# Comment out: /usr/bin/systemctl poweroff
# Add: log "TEST: Would trigger shutdown here"

# Manually trigger LOW IGNITION (if you have control of GPIO)
# OR wait for actual vehicle IGNITION disconnect

# Watch logs
journalctl -u smartassist-gpio-monitor -f
```

### **Production Testing:**
1. Start vehicle (IGNITION ON)
2. Check logs show: "IGNITION is ON"
3. Turn off vehicle (IGNITION OFF)
4. System should:
   - Log "IGNITION is OFF"
   - Stop pipeline
   - Power off within 15-20 seconds

---

## Dependencies

**Requires:**
- `smartassist-gpio-export.service` - GPIO must be exported first

**Required by:**
- None (monitors system, triggers shutdown)

**Related:**
- `smartassist-pipeline.service` - Service being monitored/stopped

---

## Configuration

Edit script to customize behavior:

```bash
sudo nano /opt/smartassist/services/gpio-monitor/src/monitor.sh
```

**Configurable parameters:**
```bash
GPIO_PIN="PH.01"              # GPIO pin for IGNITION
LOCK_FILE="/run/lock/..."     # Prevent concurrent runs
PIPELINE_SERVICE="..."        # Service to stop gracefully
```

**Timer interval:**
```bash
sudo nano /etc/systemd/system/smartassist-gpio-monitor.timer
```
```ini
OnUnitActiveSec=5sec  # Check every 5 seconds
OnBootSec=10sec       # Wait 10s after boot before first check
```

---

## Troubleshooting

### Timer not running

**Problem:** Timer not active

**Solution:**
```bash
# Check timer status
systemctl status smartassist-gpio-monitor.timer

# Enable timer (not service!)
sudo systemctl enable smartassist-gpio-monitor.timer
sudo systemctl start smartassist-gpio-monitor.timer

# Verify timer is in list
systemctl list-timers
```

### Script fails: "GPIO pin not found"

**Problem:** GPIO export service not running

**Solution:**
```bash
# Check GPIO export service
systemctl status smartassist-gpio-export

# Test GPIO manually
gpiodetect
gpiofind PH.01

# Restart GPIO export
sudo systemctl restart smartassist-gpio-export
```

### IGNITION always reads as OFF

**Problem:** Wiring issue or inverted logic

**Solution:**
```bash
# Read GPIO state manually
gpioget $(gpiofind PH.01)

# If inverted (reads 0 when ON), modify script logic:
# Change: if [ "$GPIO_STATE" == "1" ]
# To:     if [ "$GPIO_STATE" == "0" ]
```

### System shuts down immediately after boot

**Problem:** IGNITION signal not connected or inverted

**Solution:**
```bash
# Disable timer temporarily
sudo systemctl stop smartassist-gpio-monitor.timer
sudo systemctl disable smartassist-gpio-monitor.timer

# Check IGNITION wiring
gpioget $(gpiofind PH.01)
# Should read 1 when vehicle is ON

# If 0, check:
# - IGNITION wire connection
# - Vehicle power state
# - GPIO signal level (3.3V?)
```

### Pipeline doesn't stop gracefully

**Problem:** 10 second timeout too short

**Solution:**
```bash
# Edit script to increase timeout
sudo nano /opt/smartassist/services/gpio-monitor/src/monitor.sh

# Change: sleep 10
# To:     sleep 30  # Or longer
```

---

## Safety Features

### **Lock File:**
- Prevents concurrent script runs
- Cleaned up automatically on exit

### **Graceful Shutdown:**
- Stops pipeline service first (10s grace period)
- Gives time for log/video saving
- Force kills only if not responding

### **Logging:**
- All actions logged to systemd journal
- Visible in: `journalctl -u smartassist-gpio-monitor`
- Helps diagnose shutdown issues

---

## Hardware Details

**GPIO Pin:** PH.01  
**Signal:** IGNITION from vehicle  
**Logic:** HIGH = Ignition ON, LOW = Ignition OFF  
**Voltage:** 3.3V digital input  
**Check Interval:** 5 seconds  
**Shutdown Delay:** 10-15 seconds total

---

## Flow Diagram

```
Boot
  ↓
Wait 10s
  ↓
Start Timer ───┐
  ↓            │
Every 5s ←─────┘
  ↓
Read GPIO PH.01
  ↓
  ├─ HIGH (1) → Log "IGNITION ON" → Continue
  │
  └─ LOW (0) → Log "IGNITION OFF"
               ↓
               Stop pipeline (10s grace)
               ↓
               Force kill if needed
               ↓
               Trigger poweroff
               ↓
               System shuts down
```

---

## Notes

- **CRITICAL:** This service triggers real shutdowns!
- Timer runs continuously while system is on
- Service is triggered BY timer (don't start service directly)
- Monitor with: `journalctl -u smartassist-gpio-monitor -f`
- Adjust check interval in timer file if needed
- Test in safe environment before vehicle deployment

---

## Related Services

- **smartassist-gpio-export.service** - Must run first
- **smartassist-pipeline.service** - Service being monitored
- **smartassist-gpio-monitor.timer** - Triggers this service
