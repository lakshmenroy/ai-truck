# Time Sync Service

**Purpose:** Synchronize system time from GPS timestamp on vehicle CAN bus

---

## Overview

The Jetson may not have a battery-backed RTC, causing incorrect system time on boot. This service listens to the vehicle CAN bus for GPS time messages and synchronizes the system clock. If GPS time is unavailable, it uses the last known time + 1 minute as a fallback.

Accurate time is critical for:
- Correct log file timestamps
- Video file metadata
- Event sequencing
- Troubleshooting

---

## What It Does

1. **Listen for GPS Time:** Monitors CAN bus for GPS timestamp messages
2. **Set System Time:** Updates system clock when GPS time received
3. **Fallback Method:** Uses last known time + 1 min if GPS unavailable
4. **Save Last Known:** Periodically saves current time to file
5. **Retry:** Retries every 5 minutes if time sync fails

---

## Installation

```bash
# Install Python dependencies
pip3 install -r services/time-sync/requirements.txt

# Or system packages
sudo apt install python3-can python3-cantools

# Make script executable
chmod +x services/time-sync/src/can_time_sync.py

# Copy files to system location
sudo mkdir -p /opt/smartassist/services/time-sync/src
sudo cp services/time-sync/src/can_time_sync.py /opt/smartassist/services/time-sync/src/
sudo chmod +x /opt/smartassist/services/time-sync/src/can_time_sync.py

sudo cp services/time-sync/smartassist-time-sync.service /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable service
sudo systemctl enable smartassist-time-sync

# Start service
sudo systemctl start smartassist-time-sync
```

---

## Testing

```bash
# Check service status
systemctl status smartassist-time-sync

# View logs
journalctl -u smartassist-time-sync -f

# Check system time
date

# Manual test (with CAN time message)
sudo python3 /opt/smartassist/services/time-sync/src/can_time_sync.py
```

---

## Configuration

### **Update DBC Message/Signal Names:**

Edit `can_time_sync.py`:

```python
# Configuration
CAN_INTERFACE = 'can0'
DBC_FILE = '/opt/smartassist/pipeline/dbc/TMS_V1_45_20251110.dbc'
TIME_MESSAGE_NAME = 'GPS_Time'      # ← Update with actual message name
TIME_SIGNAL_NAME = 'timestamp'      # ← Update with actual signal name
TIMEOUT = 300  # 5 minutes
```

### **Find Correct Message Names:**

```bash
# Use cantools to inspect DBC
python3 << EOF
import cantools
db = cantools.database.load_file('/path/to/your.dbc')
for msg in db.messages:
    print(f'{msg.name} (0x{msg.frame_id:X}):')
    for sig in msg.signals:
        print(f'  - {sig.name}')
EOF
```

### **Update Time Conversion:**

The script currently assumes Unix timestamp. Update if your DBC uses different format:

```python
# Example: GPS week/second format
gps_week = data['GPS_Week']
gps_second = data['GPS_Second']
gps_time = gps_epoch + timedelta(weeks=gps_week, seconds=gps_second)
```

---

## Dependencies

**Requires:**
- `smartassist-can-init.service` - CAN bus must be initialized
- `network.target` - Network subsystem

**Required by:**
- `smartassist-pipeline.service` - Runs before pipeline (recommended)

---

## Troubleshooting

### Service fails: "DBC file not found"

**Problem:** DBC file path incorrect

**Solution:**
```bash
# Find DBC file
find /opt/smartassist -name "*.dbc"

# Update path in script
sudo nano /opt/smartassist/services/time-sync/src/can_time_sync.py
# Change: DBC_FILE = '/path/to/correct.dbc'
```

### Service fails: "Message not found in DBC"

**Problem:** TIME_MESSAGE_NAME doesn't match DBC

**Solution:**
```bash
# List all messages in DBC
python3 << EOF
import cantools
db = cantools.database.load_file('/path/to/your.dbc')
for msg in db.messages:
    print(msg.name)
EOF

# Update TIME_MESSAGE_NAME in script
```

### Service fails: "Signal not found in message"

**Problem:** TIME_SIGNAL_NAME doesn't match DBC

**Solution:**
```bash
# List signals in message
python3 << EOF
import cantools
db = cantools.database.load_file('/path/to/your.dbc')
msg = db.get_message_by_name('YourMessageName')
for sig in msg.signals:
    print(sig.name)
EOF

# Update TIME_SIGNAL_NAME in script
```

### Time never syncs (timeout)

**Problem:** No GPS time message on CAN bus

**Solution:**
```bash
# Monitor CAN bus for time messages
candump can0 | grep GPS

# Check if vehicle is sending GPS data
# May need vehicle to be moving or have GPS lock

# Check fallback time is working
cat /var/lib/smartassist/last_known_time.txt
```

### Fallback time incorrect

**Problem:** Last known time file corrupted or old

**Solution:**
```bash
# Set time manually once
sudo timedatectl set-time "2025-12-12 14:30:00"

# Service will save this as last known time
```

### Permission denied setting time

**Problem:** Insufficient capabilities

**Solution:**
```bash
# Verify service has CAP_SYS_TIME
systemctl show smartassist-time-sync | grep Ambient

# Should show: AmbientCapabilities=CAP_SYS_TIME

# If not, reinstall service file
```

---

## How It Works

```
Boot
  ↓
Wait for CAN init
  ↓
Start Time Sync Service
  ↓
Load DBC file
  ↓
Listen to CAN (5 min timeout)
  ↓
  ├─ GPS message received?
  │  ├─ YES → Decode timestamp
  │  │        ↓
  │  │        Set system time
  │  │        ↓
  │  │        Save to fallback file
  │  │        ↓
  │  │        SUCCESS → Exit
  │  │
  │  └─ NO (timeout)
  │     ↓
  │     Load last known time
  │     ↓
  │     Add 1 minute
  │     ↓
  │     Set system time
  │     ↓
  │     FALLBACK SUCCESS → Exit
  ↓
Service exits (or retries every 5 min)
```

---

## Fallback File Location

```
/var/lib/smartassist/last_known_time.txt
```

**Format:** ISO 8601 timestamp  
**Example:** `2025-12-12T14:30:45.123456`

**Manually set fallback:**
```bash
sudo mkdir -p /var/lib/smartassist
echo "2025-12-12T14:30:00" | sudo tee /var/lib/smartassist/last_known_time.txt
```

---

## Notes

- Service runs once at boot (then exits or retries every 5 min)
- GPS time may take 30-60 seconds to appear on CAN
- Fallback prevents wildly incorrect times
- Accurate to within ±1 minute if GPS unavailable
- Update DBC message/signal names for your vehicle
- Monitor with: `journalctl -u smartassist-time-sync -f`

---

## Related Services

- **smartassist-can-init.service** - Must run first
- **smartassist-pipeline.service** - Benefits from accurate time
- **smartassist-camera-init.service** - Uses time for file naming
