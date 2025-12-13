# SmartAssist Installation Guide

Complete step-by-step installation guide for NVIDIA Jetson Orin edge devices.

---

## 📋 Prerequisites

### Hardware Requirements

**Required:**
- NVIDIA Jetson Orin (AGX or NX)
- 4x GMSL cameras with LVDS interface
- CAN bus connection to vehicle (can0)
- GPIO connection for IGNITION signal (PH.01)
- microSD card or NVMe SSD (64GB+ recommended)

**Optional:**
- Network connectivity (for updates)
- RTSP/UDP monitoring station

### Software Requirements

**Pre-installed (via SDK Manager):**
- Ubuntu 20.04 or 22.04
- JetPack 6.0+
- CUDA 12.2+
- cuDNN 8.9+
- TensorRT 8.6+
- DeepStream 6.4+

**To be installed:**
- Python 3.8+
- GStreamer 1.20+
- System libraries
- Python packages

---

## 🚀 Installation Steps

### Step 1: Flash Jetson with JetPack

**Using NVIDIA SDK Manager:**

1. Download SDK Manager from NVIDIA
2. Connect Jetson via USB-C in recovery mode
3. Select JetPack 6.0 or newer
4. Flash with DeepStream SDK included
5. Wait for completion (~30-60 minutes)

**Verify JetPack:**
```bash
# Check JetPack version
sudo apt-cache show nvidia-jetpack

# Verify CUDA
nvcc --version

# Verify DeepStream
deepstream-app --version
```

### Step 2: System Preparation

**Update system:**
```bash
sudo apt update
sudo apt upgrade -y
```

**Install essential tools:**
```bash
sudo apt install -y \
    git \
    vim \
    htop \
    tmux \
    net-tools \
    can-utils \
    libgpiod-dev \
    libgpiod2 \
    gpiod
```

**Set performance mode:**
```bash
# Max performance
sudo nvpmodel -m 0
sudo jetson_clocks

# Make persistent (add to /etc/rc.local if needed)
```

### Step 3: Clone Repository

**Choose installation location:**
```bash
# Recommended: /opt/smartassist
cd /opt
sudo git clone <repository-url> smartassist

# Set permissions
sudo chown -R $USER:$USER /opt/smartassist
cd smartassist
```

**Alternative locations work too** (thanks to smart path detection):
```bash
# Home directory
cd ~
git clone <repository-url> smartassist

# Any location
cd /path/to/your/choice
git clone <repository-url> smartassist
```

### Step 4: Install System Dependencies

**Install Python and GStreamer:**
```bash
sudo apt install -y \
    python3 \
    python3-pip \
    python3-dev \
    python3-gi \
    python3-gi-cairo \
    gstreamer1.0-tools \
    gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad \
    gstreamer1.0-plugins-ugly \
    gstreamer1.0-libav \
    libgstreamer1.0-dev \
    libgstreamer-plugins-base1.0-dev \
    gir1.2-gstreamer-1.0
```

**Install OpenCV and NumPy:**
```bash
sudo apt install -y \
    python3-opencv \
    python3-numpy \
    libopencv-dev
```

**Install CAN utilities:**
```bash
sudo apt install -y \
    can-utils \
    iproute2
```

### Step 5: Install Python Dependencies

**Install from requirements.txt:**
```bash
cd /opt/smartassist
sudo pip3 install -r requirements.txt
```

**Manual installation (if needed):**
```bash
sudo pip3 install \
    numpy \
    opencv-python \
    pyyaml \
    python-can \
    cantools
```

**Install DeepStream Python bindings:**
```bash
cd /opt/nvidia/deepstream/deepstream/lib
sudo python3 setup.py install
```

**Verify imports:**
```bash
python3 << EOF
import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst
import pyds
import numpy as np
import cv2
import yaml
import can
import cantools
print("✅ All Python imports successful")
EOF
```

### Step 6: Configure CAN Interface

**Load CAN modules:**
```bash
sudo modprobe can
sudo modprobe can_raw
sudo modprobe mttcan  # For Jetson Orin
```

**Make persistent:**
```bash
# Add to /etc/modules-load.d/can.conf
echo "can" | sudo tee /etc/modules-load.d/can.conf
echo "can_raw" | sudo tee -a /etc/modules-load.d/can.conf
echo "mttcan" | sudo tee -a /etc/modules-load.d/can.conf
```

**Test CAN interface:**
```bash
# Should show can0 and can1
ip link show | grep can
```

### Step 7: Configure GPIO

**Install GPIO tools:**
```bash
sudo apt install -y libgpiod-dev libgpiod2 gpiod
```

**Test GPIO access:**
```bash
# Find IGNITION pin
gpiofind PH.01

# Read state (should work without error)
gpioget $(gpiofind PH.01)
```

**Set GPIO permissions:**
```bash
# Add user to gpio group (if exists)
sudo usermod -aG gpio $USER

# Log out and back in for changes to take effect
```

### Step 8: Install System Services

**Run installation script:**
```bash
cd /opt/smartassist
sudo ./install_services.sh
```

**What this installs:**
- GPIO export service
- CAN init/deinit services
- Time sync service (with timer)
- GPIO monitor service (with timer)
- CAN server service
- Camera init service
- Health monitor service (with timer)
- Pipeline service

**Verify installation:**
```bash
# List installed services
systemctl list-unit-files | grep smartassist

# Should show:
# smartassist-gpio-export.service
# smartassist-can-init.service
# smartassist-can-deinit.service
# smartassist-can-server.service
# smartassist-time-sync.service
# smartassist-time-sync.timer
# smartassist-camera-init.service
# smartassist-pipeline.service
# smartassist-gpio-monitor.service
# smartassist-gpio-monitor.timer
# smartassist-health-monitor.service
# smartassist-health-monitor.timer
```

### Step 9: Configuration

**Customize camera configuration:**
```bash
cd /opt/smartassist/pipeline/config
sudo nano camera_config.json

# Edit camera mappings, GMSL ports, sensor modes
```

**Customize logging:**
```bash
sudo nano logging_config.yaml

# Set log level, output directory, etc.
```

**Customize model parameters:**
```bash
# CSI parameters
sudo nano /opt/smartassist/models/csi/config/csi_config.yaml

# Nozzlenet parameters
sudo nano /opt/smartassist/models/nozzlenet/config/nozzlenet_config.yaml
```

### Step 10: Validation

**Run validation script:**
```bash
cd /opt/smartassist
sudo python3 tools/validate_installation.py
```

**Expected output:**
```
✅ Python version: 3.8.10
✅ NumPy installed: 1.24.3
✅ OpenCV installed: 4.5.4
✅ GStreamer installed: 1.20.3
✅ PyDS installed: 1.1.10
✅ CAN interface can0 detected
✅ GPIO PH.01 accessible
✅ DeepStream installed: 6.4
✅ All services installed
✅ Configuration files present
✅ DBC files found

Installation validation: SUCCESS
```

**If validation fails, check:**
- Installation logs in `/var/log/smartassist/`
- Service status: `systemctl status smartassist-*`
- Missing dependencies
- Permission issues

---

## 🏃 First Run

### Start Services Manually

**Start in order:**
```bash
# 1. GPIO export (required first)
sudo systemctl start smartassist-gpio-export
systemctl status smartassist-gpio-export

# 2. CAN initialization
sudo systemctl start smartassist-can-init
ip link show can0  # Should show UP, bitrate 250000

# 3. CAN server
sudo systemctl start smartassist-can-server
systemctl status smartassist-can-server

# 4. Time sync (optional but recommended)
sudo systemctl start smartassist-time-sync.timer

# 5. Camera initialization
sudo systemctl start smartassist-camera-init
cat /tmp/camera_init_results_*.json  # Check results

# 6. Main pipeline
sudo systemctl start smartassist-pipeline
```

**Monitor pipeline:**
```bash
# Follow logs
journalctl -u smartassist-pipeline -f

# Check status
systemctl status smartassist-pipeline
```

### Enable Auto-Start

**Enable all services:**
```bash
sudo systemctl enable smartassist-gpio-export
sudo systemctl enable smartassist-can-init
sudo systemctl enable smartassist-can-server
sudo systemctl enable smartassist-time-sync.timer
sudo systemctl enable smartassist-camera-init
sudo systemctl enable smartassist-pipeline
sudo systemctl enable smartassist-gpio-monitor.timer
sudo systemctl enable smartassist-health-monitor.timer
```

**Verify enabled:**
```bash
systemctl list-unit-files | grep smartassist | grep enabled
```

**Test auto-start:**
```bash
# Reboot and check if all start automatically
sudo reboot

# After reboot:
systemctl status smartassist-*
```

---

## 🧪 Testing

### Test CAN Communication

**Monitor CAN messages:**
```bash
# On can0
candump can0

# Should see messages from vehicle
```

**Send test message:**
```bash
# Send test frame
cansend can0 123#DEADBEEF

# Verify in logs
journalctl -u smartassist-can-server | grep 123
```

### Test Camera Detection

**Check cameras:**
```bash
# List video devices
ls -la /dev/video*

# Check camera init results
cat /tmp/camera_init_results_*.json

# Should show detected cameras with GMSL ports
```

**Test camera capture:**
```bash
# Capture single frame
v4l2-ctl --device=/dev/video0 --stream-mmap --stream-count=1 --stream-to=/tmp/test.raw

# Check file created
ls -lh /tmp/test.raw
```

### Test Pipeline Output

**Check video output:**
```bash
# If UDP streaming enabled
# On monitoring computer:
ffplay udp://jetson-ip:5000

# Or VLC: udp://@:5000
```

**Check logs:**
```bash
# Should see regular FPS updates
journalctl -u smartassist-pipeline | grep FPS

# Should see nozzle detections
journalctl -u smartassist-pipeline | grep nozzle

# Should see CSI calculations
journalctl -u smartassist-pipeline | grep CSI
```

### Test IGNITION Shutdown

**⚠️ WARNING:** This will trigger actual shutdown!

```bash
# Monitor GPIO service
journalctl -u smartassist-gpio-monitor -f

# Simulate IGNITION OFF (if you can control GPIO)
# System should shutdown gracefully after ~15 seconds
```

---

## 🔧 Troubleshooting Installation

### Issue: Service won't enable

**Symptoms:**
```bash
sudo systemctl enable smartassist-pipeline
Failed to enable unit: File exists
```

**Solution:**
```bash
# Remove conflicting symlink
sudo rm /etc/systemd/system/multi-user.target.wants/smartassist-pipeline.service

# Reload and try again
sudo systemctl daemon-reload
sudo systemctl enable smartassist-pipeline
```

### Issue: Python import errors

**Symptoms:**
```
ImportError: No module named 'gi'
```

**Solution:**
```bash
# Reinstall GStreamer Python bindings
sudo apt install -y python3-gi gir1.2-gstreamer-1.0

# Verify
python3 -c "import gi; print('OK')"
```

### Issue: CAN interface not found

**Symptoms:**
```
OSError: [Errno 19] No such device: 'can0'
```

**Solution:**
```bash
# Check kernel modules
lsmod | grep can

# Load if missing
sudo modprobe mttcan
sudo modprobe can
sudo modprobe can_raw

# Make persistent
echo "mttcan" | sudo tee -a /etc/modules-load.d/can.conf
```

### Issue: GPIO access denied

**Symptoms:**
```
Permission denied: /dev/gpiochip0
```

**Solution:**
```bash
# Check GPIO group
groups | grep gpio

# Add user to group
sudo usermod -aG gpio $USER

# Log out and back in
```

### Issue: DeepStream not found

**Symptoms:**
```
ModuleNotFoundError: No module named 'pyds'
```

**Solution:**
```bash
# Install DeepStream Python bindings
cd /opt/nvidia/deepstream/deepstream/lib
sudo python3 setup.py install

# Verify
python3 -c "import pyds; print(pyds.__version__)"
```

---

## 📝 Post-Installation

### Verify All Services

**Check all service status:**
```bash
# Quick check
systemctl list-units --type=service | grep smartassist

# Detailed check
for service in gpio-export can-init can-server time-sync camera-init pipeline gpio-monitor health-monitor; do
    echo "=== smartassist-$service ==="
    systemctl status smartassist-$service --no-pager
done
```

### Set Up Log Rotation

**Create logrotate config:**
```bash
sudo nano /etc/logrotate.d/smartassist
```

**Add:**
```
/var/log/smartassist/*.log {
    daily
    rotate 7
    compress
    missingok
    notifempty
}

/mnt/ssd/logs/*.log {
    daily
    rotate 30
    compress
    missingok
    notifempty
}
```

### Configure Network (Optional)

**For UDP streaming:**
```bash
# Edit pipeline config
sudo nano /opt/smartassist/pipeline/config/pipeline_config.yaml

# Set UDP host/port
udp:
  host: 192.168.1.100
  port: 5000
```

### Backup Configuration

**Create backup:**
```bash
# Backup all configs
sudo mkdir -p /backup/smartassist
sudo cp -r /opt/smartassist/pipeline/config /backup/smartassist/
sudo cp -r /opt/smartassist/models/*/config /backup/smartassist/

# Backup service files
sudo cp /etc/systemd/system/smartassist-* /backup/smartassist/
```

---

## ✅ Installation Complete

Your SmartAssist system should now be:

- ✅ Fully installed
- ✅ Services running
- ✅ Auto-start enabled
- ✅ Validated and tested

**Next steps:**
- Review service logs: `journalctl -u smartassist-pipeline -f`
- Monitor health: `cat /var/lib/smartassist/service_status.json`
- Configure for your vehicle: Edit configs in `pipeline/config/`
- Read service docs: `services/README.md`

---

**Installation guide version:** 1.0  
**Last updated:** December 13, 2025  
**Platform:** NVIDIA Jetson Orin with JetPack 6.0+