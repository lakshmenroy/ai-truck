# 📚 SMARTASSIST

## 🎯 Overview

SmartAssist is a real-time AI vision system for intelligent street sweeping vehicles. It uses DeepStream on NVIDIA Jetson to provide:

- **Nozzle Detection:** Real-time monitoring of nozzle status (clear/blocked/check/gravel)
- **CSI Computation:** Clean Street Index calculation from road and garbage segmentation
- **CAN Integration:** Bidirectional communication with vehicle control systems
- **Multi-Camera Support:** Up to 4 GMSL cameras with LVDS interface
- **Edge Processing:** On-device inference with sub-100ms latency

---

## 📂 Project Structure

```
SmartAssist/
├── pipeline/              # Main GStreamer pipeline application
│   ├── src/              # Modular source code
│   │   ├── main.py       # Application entry point
│   │   ├── context.py    # Configuration and context management
│   │   ├── pipeline/     # GStreamer pipeline components
│   │   ├── can/          # CAN client interface
│   │   ├── monitoring/   # FPS and override monitoring
│   │   └── utils/        # Helper utilities
│   ├── config/           # Configuration files
│   ├── dbc/              # CAN database files
│   └── systemd/          # Service file
│
├── models/               # AI models (modular by model type)
│   ├── csi/             # Clean Street Index model
│   │   ├── src/         # CSI-specific code
│   │   ├── config/      # CSI configuration
│   │   └── deepstream_configs/  # DeepStream inference configs
│   └── nozzlenet/       # Nozzle detection model
│       ├── src/         # Nozzlenet-specific code
│       ├── config/      # Nozzlenet configuration
│       └── deepstream_configs/  # DeepStream inference configs
│
├── services/            # System services (independent daemons)
│   ├── gpio-export/     # GPIO pin initialization
│   ├── gpio-monitor/    # IGNITION signal monitoring
│   ├── can-init/        # CAN bus setup
│   ├── time-sync/       # GPS time synchronization
│   ├── can-server/      # CAN communication server
│   └── health-monitor/  # Service health checking
│
├── tools/               # Utilities and validation scripts
│   ├── initialize_cameras.py    # Camera detection
│   ├── validate_installation.py # System validation
│   └── set_serial_number.py     # Serial number setup
│
└── docs/                # Extended documentation
    ├── flowcharts/      # System flowcharts
    └── deployment/      # Deployment guides
```

---

## 🚀 Quick Start

### Prerequisites

**Hardware:**
- NVIDIA Jetson Orin (AGX or NX)
- 4x GMSL cameras (LVDS interface)
- CAN bus connection (can0 at 250Kbps)
- GPIO connection for IGNITION signal (PH.01)

**Software:**
- JetPack 6.0+ installed
- DeepStream 6.4+ SDK
- Ubuntu 20.04 or 22.04

### Installation

```bash
# 1. Clone repository to /opt
cd /opt
sudo git clone <repo-url> smartassist
cd smartassist

# 2. Install system dependencies
sudo apt update
sudo apt install -y python3-gi gstreamer1.0-tools libgpiod2 \
                    can-utils python3-opencv python3-numpy

# 3. Install Python dependencies
sudo pip3 install -r requirements.txt

# 4. Install system services
sudo ./install_services.sh

# 5. Validate installation
sudo python3 tools/validate_installation.py
```

### First Run

```bash
# Start services in order
sudo systemctl start smartassist-gpio-export
sudo systemctl start smartassist-can-init
sudo systemctl start smartassist-can-server
sudo systemctl start smartassist-time-sync
sudo systemctl start smartassist-camera-init
sudo systemctl start smartassist-pipeline

# Check status
systemctl status smartassist-pipeline

# View logs
journalctl -u smartassist-pipeline -f
```

### Enable Auto-Start

```bash
# Enable all services to start at boot
sudo systemctl enable smartassist-gpio-export
sudo systemctl enable smartassist-can-init
sudo systemctl enable smartassist-can-server
sudo systemctl enable smartassist-time-sync.timer
sudo systemctl enable smartassist-camera-init
sudo systemctl enable smartassist-pipeline
sudo systemctl enable smartassist-gpio-monitor.timer
sudo systemctl enable smartassist-health-monitor.timer
```

---

## 📊 System Components

### 1. Pipeline Application

**Entry Point:** `pipeline/src/main.py`

**GStreamer Topology:**
```
4x nvarguscamerasrc → tee (3-way split)
├─→ HR Output (H.265 recording)
├─→ nvstreamdemux → Inference paths
│   ├─→ Nozzle cameras → nozzlenet → State machine → CAN
│   └─→ CSI cameras → Road/Garbage segmentation → CSI calculation
└─→ nvdsmetamux → OSD → UDP/RTSP stream
```

**Key Features:**
- Multi-stream processing with synchronized inference
- Real-time OSD overlay with nozzle status and CSI
- H.265 video recording with metadata
- FPS monitoring and performance tracking
- UDP/RTSP streaming for remote monitoring

### 2. AI Models

#### CSI Model (Clean Street Index)
**Location:** `models/csi/`

**Input:** Front and rear camera feeds  
**Output:** CSI score (0-100) + discrete levels (A-D)  
**Processing:**
- Road segmentation (drivable area)
- Garbage detection (litter on road)
- Trapezoid masking for ROI
- Area calculation and CSI computation

**Configuration:** `models/csi/config/csi_config.yaml`

#### Nozzlenet Model
**Location:** `models/nozzlenet/`

**Input:** Primary and secondary nozzle cameras  
**Output:** Nozzle status (clear/blocked/check/gravel)  
**Processing:**
- Object detection for nozzle state
- State machine for status transitions
- Fan speed control logic
- CAN message generation

**Configuration:** `models/nozzlenet/config/nozzlenet_config.yaml`

### 3. System Services

| Service | Type | Purpose | Startup |
|---------|------|---------|---------|
| **gpio-export** | oneshot | Export GPIO pins for IGNITION monitoring | sysinit.target |
| **can-init** | oneshot | Initialize CAN0 at 250Kbps | network.target |
| **can-server** | daemon | CAN communication server (socket interface) | After can-init |
| **time-sync** | oneshot (hourly) | Sync system time from GPS via CAN | After can-init |
| **camera-init** | oneshot | Detect and validate cameras | After time-sync |
| **pipeline** | daemon | Main AI vision application | After camera-init |
| **gpio-monitor** | timer (5s) | Monitor IGNITION, trigger shutdown | After gpio-export |
| **health-monitor** | timer (30s) | Check service health status | After multi-user |

**See:** `services/README.md` for detailed service documentation

---

## 📖 Documentation

### Getting Started
- **[INSTALLATION.md](INSTALLATION.md)** - Detailed installation guide
- **[docs/deployment/SERVICE_STARTUP.md](docs/deployment/SERVICE_STARTUP.md)** - Service management

### Architecture
- **[pipeline/README.md](pipeline/README.md)** - Pipeline architecture details
- **[models/README.md](models/README.md)** - AI models overview
- **[services/README.md](services/README.md)** - System services details

### Migration
- **[MIGRATION_GUIDE.md](MIGRATION_GUIDE.md)** - Changes from legacy code

### Technical
- **[docs/flowcharts/NEW_PIPELINE_FLOW.md](docs/flowcharts/NEW_PIPELINE_FLOW.md)** - Pipeline execution flow
- **[docs/flowcharts/LEGACY_VS_NEW.md](docs/flowcharts/LEGACY_VS_NEW.md)** - Legacy comparison

---

## 🔧 Configuration

### Main Configuration Files

**Pipeline Settings:**
- `pipeline/config/pipeline_config.yaml` - Pipeline parameters
- `pipeline/config/logging_config.yaml` - Logging configuration
- `pipeline/config/camera_config.json` - Camera initialization

**Model Settings:**
- `models/csi/config/csi_config.yaml` - CSI computation parameters
- `models/nozzlenet/config/nozzlenet_config.yaml` - Nozzlenet settings

**DeepStream Configs:**
- `models/csi/deepstream_configs/road_config.txt` - Road segmentation
- `models/csi/deepstream_configs/garbage_config.txt` - Garbage detection
- `models/nozzlenet/deepstream_configs/infer_config.txt` - Nozzle inference

### Key Settings

**Camera Configuration** (`camera_config.json`):
```json
{
  "cameras": [
    {
      "name": "primary_nozzle",
      "gmsl_port": "5",
      "sensor_mode": 3,
      "do_infer": true
    }
  ]
}
```

**CSI Parameters** (`csi_config.yaml`):
```yaml
trapezoid:
  top_width_ratio: 0.3
  bottom_width_ratio: 1.0
  height_ratio: 0.7
```

**Logging** (`logging_config.yaml`):
```yaml
logging:
  log_level: INFO
  save_logs: true
  log_directory: /mnt/ssd/logs
```

---

## 🐛 Troubleshooting

### Pipeline Won't Start

**Symptoms:** Service fails immediately or won't reach active state

**Check:**
```bash
# 1. Check dependencies
systemctl status smartassist-camera-init
systemctl status smartassist-can-server

# 2. View detailed logs
journalctl -u smartassist-pipeline -n 100 --no-pager

# 3. Check camera initialization
cat /tmp/camera_init_results_*.json

# 4. Verify CAN bus
ip link show can0
```

**Common Fixes:**
```bash
# Restart dependencies
sudo systemctl restart smartassist-camera-init
sudo systemctl restart smartassist-can-server

# Re-initialize CAN
sudo systemctl restart smartassist-can-init
```

### CAN Communication Fails

**Symptoms:** No CAN data in logs, state machine not updating

**Check:**
```bash
# Verify CAN interface is UP
ip link show can0
# Should show: "state UP, bitrate 250000"

# Monitor CAN messages
candump can0

# Check CAN server
systemctl status smartassist-can-server
```

**Common Fixes:**
```bash
# Restart CAN stack
sudo systemctl restart smartassist-can-init
sudo systemctl restart smartassist-can-server
sleep 5
sudo systemctl restart smartassist-pipeline
```

### Cameras Not Detected

**Symptoms:** Camera init fails, "No cameras found"

**Check:**
```bash
# Check camera init results
cat /tmp/camera_init_results_*.json

# Verify camera devices
ls -la /dev/video*

# Check hardware
v4l2-ctl --list-devices
```

**Common Fixes:**
```bash
# Re-run camera initialization
sudo systemctl restart smartassist-camera-init

# If persistent, check physical connections
# Verify GMSL cables are seated properly
```

### Performance Issues

**Symptoms:** Low FPS, high CPU usage, dropped frames

**Check:**
```bash
# Check resource usage
htop

# Monitor GPU
tegrastats

# Check pipeline stats
journalctl -u smartassist-pipeline | grep FPS
```

**Common Fixes:**
```bash
# Increase GPU clocks
sudo nvpmodel -m 0  # Max performance mode
sudo jetson_clocks

# Reduce processing load (edit configs)
# - Lower resolution
# - Reduce inference batch size
# - Disable non-essential outputs
```

### IGNITION Shutdown Not Working

**Symptoms:** System doesn't shut down when ignition turned off

**Check:**
```bash
# Verify GPIO export
gpioget $(gpiofind PH.01)

# Check monitor service
systemctl status smartassist-gpio-monitor.timer
journalctl -u smartassist-gpio-monitor -f
```

**Common Fixes:**
```bash
# Restart GPIO services
sudo systemctl restart smartassist-gpio-export
sudo systemctl restart smartassist-gpio-monitor.timer
```

---

## 📈 Monitoring

### Service Health

**Check all services:**
```bash
# View health status JSON
cat /var/lib/smartassist/service_status.json

# List all SmartAssist services
systemctl list-units --type=service | grep smartassist
```

**Monitor continuously:**
```bash
# Watch service status
watch -n 5 'systemctl status smartassist-*'
```

### Logs

**Pipeline logs:**
```bash
# Follow pipeline logs
journalctl -u smartassist-pipeline -f

# Last 100 lines
journalctl -u smartassist-pipeline -n 100

# Errors only
journalctl -u smartassist-pipeline -p err
```

**All SmartAssist logs:**
```bash
# All services
journalctl -t smartassist-* -f

# Since boot
journalctl -t smartassist-* -b
```

**Service-specific logs:**
```bash
# Health monitor
tail -f /var/log/smartassist/health-monitor.log

# Application logs (if configured)
tail -f /mnt/ssd/logs/smartassist_*.log
```

### Performance Metrics

**FPS monitoring:**
```bash
# Pipeline FPS (in logs)
journalctl -u smartassist-pipeline | grep "FPS:"

# GPU utilization
tegrastats --interval 1000
```

**CAN statistics:**
```bash
# CAN interface stats
ip -statistics link show can0

# Message rate
candump can0 | pv -l >/dev/null
```

---

## 🔐 Security Considerations

### Service Permissions

Most services run as `root` due to hardware requirements:
- GPIO access requires root
- CAN interface manipulation requires `CAP_NET_ADMIN`
- Video device access requires video group membership
- System time setting requires `CAP_SYS_TIME`

### Network Access

- CAN bus is isolated from internet
- UDP stream should be on isolated network
- No inbound connections accepted
- All communication is one-way (device → vehicle/monitoring)

### Data Privacy

- Video is stored locally on device
- No cloud upload by default
- CAN data logged locally
- GPS coordinates in CAN messages (be aware for GDPR)

---

## 🔄 Updates and Maintenance

### Update Process

```bash
# 1. Stop services
sudo systemctl stop smartassist-pipeline
sudo systemctl stop smartassist-can-server

# 2. Pull updates
cd /opt/smartassist
sudo git pull

# 3. Reinstall if needed
sudo ./install_services.sh

# 4. Restart services
sudo systemctl daemon-reload
sudo systemctl start smartassist-can-server
sudo systemctl start smartassist-pipeline
```

### Backup Important Data

```bash
# Configuration
sudo cp -r /opt/smartassist/pipeline/config /backup/

# Logs (if needed)
sudo cp -r /mnt/ssd/logs /backup/

# Service customizations
sudo cp /etc/systemd/system/smartassist-* /backup/
```

---

## 🤝 Contributing

See `docs/DEVELOPMENT.md` for development guidelines.

**Code Style:**
- Python: PEP 8
- Bash: ShellCheck compliant
- Comments: Docstrings for all functions

---

## 📄 License

Proprietary - All rights reserved

---

## 🆘 Support

**Issues:**
- Check troubleshooting section above
- Review logs: `journalctl -u smartassist-pipeline`
- Validate system: `python3 tools/validate_installation.py`

**Documentation:**
- `docs/` - Extended documentation
- `services/*/README.md` - Service-specific docs
- `models/*/README.md` - Model-specific docs

**Logs:**
- Journal: `journalctl -t smartassist-*`
- Health: `/var/log/smartassist/health-monitor.log`
- Application: `/mnt/ssd/logs/` (if configured)

---

**Project:** SmartAssist AI Vision System  
**Platform:** NVIDIA Jetson Orin  
**Framework:** DeepStream 6.4 + GStreamer  
**Last Updated:** December 13, 2025  
**Version:** 2.0 (Restructured)