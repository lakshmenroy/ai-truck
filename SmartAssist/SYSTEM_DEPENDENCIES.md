# SmartAssist System Dependencies

This document lists ALL system-level dependencies required for SmartAssist to run properly.

---

## 📋 **Overview**

SmartAssist requires:
1. **Python packages** (installed via pip) 
2. **System packages** (installed via apt)
3. **NVIDIA software** (installed via SDK Manager or manual download)

---

## 🐍 **Python Dependencies**

Install Python packages:
```bash
cd /path/to/SmartAssist
pip3 install -r requirements.txt
pip3 install -r pipeline/requirements.txt
pip3 install -r services/can-server/requirements.txt
```

**Or use Make:**
```bash
make install
```

---

## 📦 **System Package Dependencies**

### **GStreamer (Required)**

```bash
# GStreamer core
sudo apt-get update
sudo apt-get install -y \
    gstreamer1.0-tools \
    gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad \
    gstreamer1.0-plugins-ugly \
    gstreamer1.0-libav

# Python GStreamer bindings
sudo apt-get install -y \
    python3-gi \
    python3-gi-cairo \
    gir1.2-gstreamer-1.0 \
    gir1.2-gst-plugins-base-1.0 \
    gir1.2-glib-2.0

# GStreamer RTSP server development files
sudo apt-get install -y libgstrtspserver-1.0-dev
```

**Verify GStreamer installation:**
```bash
gst-inspect-1.0 --version
python3 -c "import gi; gi.require_version('Gst', '1.0'); from gi.repository import Gst; print('GStreamer OK')"
```

---

### **Scientific Computing Libraries**

```bash
sudo apt-get install -y \
    libopenblas-base \
    libopenmpi-dev \
    libomp-dev
```

---

### **CAN Bus Utilities**

```bash
sudo apt-get install -y can-utils
```

**Verify CAN tools:**
```bash
candump --help
cansend --help
```

---

### **Build Tools (Optional - for development)**

```bash
sudo apt-get install -y \
    build-essential \
    cmake \
    git \
    pkg-config
```

---

## 🎮 **NVIDIA Dependencies**

### **NVIDIA Jetson Requirements**

SmartAssist is designed for **NVIDIA Jetson Orin** platforms.

**Required NVIDIA Software:**
- **JetPack 6.0+** (includes CUDA, cuDNN, TensorRT)
- **DeepStream SDK 6.4+**
- **VPI 2.3+** (Vision Programming Interface)

---

### **Installing DeepStream SDK**

#### **Option 1: Via SDK Manager** (Recommended)
```bash
# Download SDK Manager from NVIDIA Developer site
# https://developer.nvidia.com/sdk-manager

# Launch SDK Manager and select:
# - Target Hardware: Jetson Orin
# - DeepStream SDK 6.4
# - Follow on-screen instructions
```

#### **Option 2: Manual Installation**
```bash
# Download DeepStream from:
# https://developer.nvidia.com/deepstream-sdk

# For Jetson (example - check NVIDIA site for latest version):
sudo apt install ./deepstream-6.4_6.4.0-1_arm64.deb

# Install DeepStream Python bindings
cd /opt/nvidia/deepstream/deepstream/lib
python3 setup.py install
```

---

### **Verify NVIDIA Installation**

```bash
# Check CUDA
nvcc --version

# Check TensorRT
dpkg -l | grep TensorRT

# Check DeepStream
deepstream-app --version

# Check DeepStream Python bindings
python3 -c "import pyds; print('PyDS version:', pyds.__version__)"

# Check VPI
dpkg -l | grep vpi
```

---

## 🔧 **Optional Dependencies**

### **Torch2TRT (For Model Conversion)**

If you need to convert PyTorch models to TensorRT:

```bash
git clone https://github.com/NVIDIA-AI-IOT/torch2trt
cd torch2trt
python3 setup.py install
```

---

### **Development Tools**

```bash
# Code formatting and linting
pip3 install black flake8 mypy

# Testing
pip3 install pytest pytest-cov

# Documentation
pip3 install sphinx sphinx-rtd-theme
```

---

## 🚀 **Quick Setup Script**

Save as `install_system_deps.sh`:

```bash
#!/bin/bash
# SmartAssist System Dependencies Installation Script

set -e

echo "Installing SmartAssist system dependencies..."

# Update package list
sudo apt-get update

# GStreamer
echo "Installing GStreamer..."
sudo apt-get install -y \
    gstreamer1.0-tools \
    gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad \
    gstreamer1.0-plugins-ugly \
    gstreamer1.0-libav \
    python3-gi \
    python3-gi-cairo \
    gir1.2-gstreamer-1.0 \
    gir1.2-gst-plugins-base-1.0 \
    gir1.2-glib-2.0 \
    libgstrtspserver-1.0-dev

# Scientific libraries
echo "Installing scientific libraries..."
sudo apt-get install -y \
    libopenblas-base \
    libopenmpi-dev \
    libomp-dev

# CAN utilities
echo "Installing CAN utilities..."
sudo apt-get install -y can-utils

echo "System dependencies installed successfully!"
echo ""
echo "⚠️  IMPORTANT: You still need to install:"
echo "   1. NVIDIA DeepStream SDK (via SDK Manager or manual download)"
echo "   2. Python dependencies (run: pip3 install -r requirements.txt)"
```

**Run the script:**
```bash
chmod +x install_system_deps.sh
./install_system_deps.sh
```

---

## ✅ **Verification Checklist**

After installation, verify all dependencies:

```bash
# Python 3.8+
python3 --version

# NumPy
python3 -c "import numpy; print('NumPy:', numpy.__version__)"

# OpenCV
python3 -c "import cv2; print('OpenCV:', cv2.__version__)"

# GStreamer
gst-inspect-1.0 --version
python3 -c "import gi; gi.require_version('Gst', '1.0'); from gi.repository import Gst; print('GStreamer OK')"

# CUDA (Jetson only)
nvcc --version

# DeepStream (Jetson only)
deepstream-app --version

# PyDS (Jetson only)
python3 -c "import pyds; print('PyDS:', pyds.__version__)"

# CAN utilities
candump --help >/dev/null 2>&1 && echo "CAN tools OK"

# SmartAssist imports
python3 -c "from pipeline.utils import paths; print('SmartAssist imports OK')"
```

**Expected output:** All commands should succeed without errors.

---

## 🐛 **Troubleshooting**

### **GStreamer Import Errors**

**Problem:** `ImportError: cannot import name 'Gst' from 'gi.repository'`

**Solution:**
```bash
sudo apt-get install python3-gi gir1.2-gstreamer-1.0
```

---

### **PyDS Not Found**

**Problem:** `ModuleNotFoundError: No module named 'pyds'`

**Solution:**
```bash
# Install DeepStream Python bindings
cd /opt/nvidia/deepstream/deepstream/lib
python3 setup.py install
```

---

### **OpenCV ImportError**

**Problem:** `ImportError: libGL.so.1: cannot open shared object file`

**Solution:**
```bash
sudo apt-get install libgl1-mesa-glx
```

---

### **CAN Interface Not Found**

**Problem:** `OSError: [Errno 19] No such device`

**Solution:**
```bash
# Enable CAN interfaces
sudo modprobe can
sudo ip link set can0 type can bitrate 500000
sudo ip link set can0 up

# Make persistent (add to /etc/network/interfaces):
auto can0
iface can0 inet manual
    pre-up /sbin/ip link set $IFACE type can bitrate 500000
    up /sbin/ifconfig $IFACE up
```

---

## 📞 **Support**

For installation issues:
1. Check this document first
2. Review DEPLOYMENT.md for deployment-specific guidance  
3. Check GitHub issues
4. Contact support team

---

**Last Updated:** December 12, 2025  
**Compatible With:** Ubuntu 20.04+, JetPack 6.0+, DeepStream 6.4+