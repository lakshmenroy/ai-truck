# Health Monitor Service

**Purpose:** Monitor health of all SmartAssist services and report status

---

## Overview

This service periodically checks the status of all `smartassist-*` services and:
- Logs service health to journal
- Writes status to JSON file
- Detects failed or inactive services
- Helps with troubleshooting and diagnostics

Runs every 30 seconds to provide near real-time service health monitoring.

---

## What It Does

1. **List Services:** Finds all `smartassist-*` services
2. **Check Status:** Determines if each service is active/failed/inactive
3. **Log Results:** Writes to systemd journal and log file
4. **Generate JSON:** Creates machine-readable status file
5. **Summary:** Reports total/active/failed/inactive counts

---

## Installation

```bash
# Make script executable
chmod +x services/health-monitor/src/check_services.sh

# Copy files to system location
sudo mkdir -p /opt/smartassist/services/health-monitor/src
sudo cp services/health-monitor/src/check_services.sh /opt/smartassist/services/health-monitor/src/
sudo chmod +x /opt/smartassist/services/health-monitor/src/check_services.sh

sudo cp services/health-monitor/smartassist-health-monitor.service /etc/systemd/system/
sudo cp services/health-monitor/smartassist-health-monitor.timer /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable timer (NOT service directly!)
sudo systemctl enable smartassist-health-monitor.timer

# Start timer
sudo systemctl start smartassist-health-monitor.timer
```

---

## Testing

```bash
# Check timer status
systemctl status smartassist-health-monitor.timer

# List timer schedule
systemctl list-timers smartassist-health-monitor.timer

# View logs (should see health checks every 30s)
journalctl -u smartassist-health-monitor -f

# View JSON status
cat /var/lib/smartassist/service_status.json

# View log file
tail -f /var/log/smartassist/health-monitor.log

# Manual test
sudo /opt/smartassist/services/health-monitor/src/check_services.sh
```

---

## Output Files

### **JSON Status File:**
**Location:** `/var/lib/smartassist/service_status.json`

**Format:**
```json
{
  "timestamp": "2025-12-12T14:30:45+00:00",
  "services": {
    "smartassist-can-server.service": {
      "status": "active",
      "since": "Thu 2025-12-12 10:00:00 UTC"
    },
    "smartassist-pipeline.service": {
      "status": "active",
      "since": "Thu 2025-12-12 10:00:15 UTC"
    },
    "smartassist-gpio-monitor.service": {
      "status": "failed"
    }
  },
  "summary": {
    "total": 8,
    "active": 7,
    "failed": 1,
    "inactive": 0
  }
}
```

### **Log File:**
**Location:** `/var/log/smartassist/health-monitor.log`

**Format:**
```
2025-12-12 14:30:45 - Checking SmartAssist services...
2025-12-12 14:30:45 - SUCCESS: ✓ smartassist-can-server.service is ACTIVE
2025-12-12 14:30:45 - ERROR: ✗ smartassist-gpio-monitor.service is FAILED
...
```

---

## Dependencies

**Requires:**
- `multi-user.target` - System fully booted

**Required by:**
- None (monitors other services)

---

## Configuration

Edit script to customize:

```bash
sudo nano /opt/smartassist/services/health-monitor/src/check_services.sh
```

**Configurable parameters:**
```bash
SERVICE_PREFIX="smartassist-"              # Service name pattern
LOG_FILE="/var/log/smartassist/health-monitor.log"
STATUS_FILE="/var/lib/smartassist/service_status.json"
```

**Timer interval:**
```bash
sudo nano /etc/systemd/system/smartassist-health-monitor.timer
```
```ini
OnUnitActiveSec=30sec  # Check every 30 seconds
OnBootSec=60sec        # Wait 60s after boot
```

---

## Troubleshooting

### Timer not running

**Problem:** Timer not active

**Solution:**
```bash
# Check timer status
systemctl status smartassist-health-monitor.timer

# Enable and start timer
sudo systemctl enable smartassist-health-monitor.timer
sudo systemctl start smartassist-health-monitor.timer

# Verify in timer list
systemctl list-timers
```

### Script fails: "Permission denied"

**Problem:** Script not executable

**Solution:**
```bash
sudo chmod +x /opt/smartassist/services/health-monitor/src/check_services.sh
```

### No services found

**Problem:** No smartassist-* services installed

**Solution:**
```bash
# List all installed services
systemctl list-units --type=service | grep smartassist

# Install missing services first
```

### JSON file not created

**Problem:** Directory doesn't exist or permissions issue

**Solution:**
```bash
# Create directory
sudo mkdir -p /var/lib/smartassist

# Set permissions
sudo chmod 755 /var/lib/smartassist

# Test script manually
sudo /opt/smartassist/services/health-monitor/src/check_services.sh
```

---

## Integration Ideas

### **Send Alerts to CAN:**
Modify script to send service status to CAN bus:

```bash
# Add at end of script
if [ "$FAILED" -gt 0 ]; then
    # Send alert to CAN
    cansend can0 0x7FF#0100000000000000
fi
```

### **Web Dashboard:**
Serve JSON file via web server:

```bash
# In nginx config
location /health {
    alias /var/lib/smartassist/service_status.json;
}
```

### **Prometheus Metrics:**
Export metrics for monitoring:

```bash
# Create metrics file
echo "smartassist_services_total $TOTAL" > /var/lib/node_exporter/smartassist.prom
echo "smartassist_services_active $ACTIVE" >> /var/lib/node_exporter/smartassist.prom
echo "smartassist_services_failed $FAILED" >> /var/lib/node_exporter/smartassist.prom
```

---

## Service List Checked

The health monitor automatically detects and checks:

- ✅ `smartassist-gpio-export.service`
- ✅ `smartassist-can-init.service`
- ✅ `smartassist-camera-init.service`
- ✅ `smartassist-can-server.service`
- ✅ `smartassist-time-sync.service`
- ✅ `smartassist-pipeline.service`
- ✅ `smartassist-gpio-monitor.service`
- ✅ `smartassist-health-monitor.service` (itself!)

And any future `smartassist-*` services added.

---

## Notes

- Checks every 30 seconds (configurable)
- Logs to both journal and file
- Creates machine-readable JSON
- Detects active/failed/inactive states
- Can be extended with CAN alerts or metrics
- Monitor with: `journalctl -u smartassist-health-monitor -f`

---

## Related Services

- All `smartassist-*` services - Being monitored
- Can be used by external monitoring systems
- Useful for troubleshooting in the field
