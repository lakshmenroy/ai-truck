# 📚 SMARTASSIST MIGRATION GUIDE



## 🎯 Overview

This guide documents the restructuring from the legacy codebase to the new SmartAssist 2.0 architecture. The migration focused on **structure improvements only** while preserving 100% of functionality.

### What Changed
- ✅ **Structure:** Monolithic → Modular
- ✅ **Organization:** Better file/folder structure
- ✅ **Paths:** Centralized path management
- ✅ **Services:** Standardized naming and organization
- ❌ **Functionality:** UNCHANGED (identical behavior)

### What Stayed the Same
- ✅ GStreamer pipeline topology
- ✅ AI model inference logic
- ✅ CAN communication protocol
- ✅ State machine behavior
- ✅ CSV logging format
- ✅ Video output formats
- ✅ Configuration parameters

---

## 📂 Directory Structure Changes

### Legacy Structure
```
/mnt/ssd/csi_pipeline/
├── pipeline_w_logging.py           # 2000+ lines monolithic file
├── can_server.py                   # Inline with pipeline
├── app_context.py
├── utils.py
├── config/
│   ├── bucher_camera_on_boot_config.json
│   ├── logging_config.yaml
│   └── nozzlenet_config.yaml
├── csi/
│   ├── bins.py
│   ├── config/
│   └── utils/
├── can/
│   ├── can_message_bus_reader.py
│   └── state_machine.py
└── dbc/

/mnt/ssd/workspace/ganindu_ws/service_automation/
├── bucher-01-gpio-export-service.d/
├── bucher-02-gpio-monitor-service.d/
├── bucher-03-can-init-service.d/
├── bucher-04-can-time-update-service.d/
├── bucher-06-camera-init-service.d/
├── bucher-07-smart-sweeper-service.d/
└── ...
```

### New Structure
```
/opt/smartassist/
├── pipeline/
│   ├── src/                        # Modular source code
│   │   ├── main.py                 # Entry point (~150 lines)
│   │   ├── context.py              # Context management
│   │   ├── pipeline/               # GStreamer components
│   │   │   ├── builder.py
│   │   │   ├── bins.py
│   │   │   ├── elements.py
│   │   │   └── linking.py
│   │   ├── can/                    # CAN client
│   │   │   └── client.py
│   │   ├── monitoring/             # Monitoring threads
│   │   │   └── threads.py
│   │   └── utils/                  # Utilities
│   │       ├── config.py
│   │       ├── paths.py
│   │       └── systemd.py
│   ├── config/
│   ├── dbc/
│   └── systemd/
│
├── models/                         # Extracted model code
│   ├── csi/
│   │   ├── src/
│   │   │   ├── bins.py
│   │   │   ├── probes.py
│   │   │   └── computation.py
│   │   ├── config/
│   │   └── deepstream_configs/
│   └── nozzlenet/
│       ├── src/
│       │   ├── bins.py
│       │   ├── probes.py
│       │   ├── state_machine.py
│       │   └── constants.py
│       ├── config/
│       └── deepstream_configs/
│
├── services/                       # Organized services
│   ├── gpio-export/
│   ├── gpio-monitor/
│   ├── can-init/
│   ├── time-sync/
│   ├── can-server/                 # Extracted from pipeline
│   └── health-monitor/             # New
│
└── tools/
```

---

## 📁 File Mapping

### Pipeline Files

| Legacy File | New Location | Changes |
|-------------|--------------|---------|
| `pipeline_w_logging.py` | Split into 8 modules | Modularized |
| → main() | `pipeline/src/main.py` | Entry point |
| → GStreamer bins | `pipeline/src/pipeline/bins.py` | Bin creation |
| → Element creation | `pipeline/src/pipeline/elements.py` | Helper functions |
| → Linking functions | `pipeline/src/pipeline/linking.py` | Pad linking |
| → Multi-camera bin | `pipeline/src/pipeline/builder.py` | Camera setup |
| → FPS monitoring | `pipeline/src/monitoring/threads.py` | Monitoring |
| → Systemd integration | `pipeline/src/utils/systemd.py` | Systemd helpers |
| `app_context.py` | `pipeline/src/context.py` | Identical functionality |
| `utils.py` | `pipeline/src/utils/config.py` | Config loading |
| **NEW** | `pipeline/src/utils/paths.py` | Smart path detection |

### Model Files

| Legacy File | New Location | Changes |
|-------------|--------------|---------|
| `pipeline/csi/bins.py` | `models/csi/src/bins.py` | Moved |
| `pipeline/csi/utils/probes/probe_functions.py` | `models/csi/src/probes.py` | Renamed |
| `pipeline/csi/utils/np_ops.py` | `models/csi/src/computation.py` | Renamed |
| Inline nozzlenet code (300+ lines) | `models/nozzlenet/src/bins.py` | Extracted |
| Inline nozzlenet probes | `models/nozzlenet/src/probes.py` | Extracted |
| `pipeline/can/state_machine.py` | `models/nozzlenet/src/state_machine.py` | Moved |
| **NEW** | `models/nozzlenet/src/constants.py` | Extracted constants |

### Configuration Files

| Legacy File | New Location | Changes |
|-------------|--------------|---------|
| `config/bucher_camera_on_boot_config.json` | `pipeline/config/camera_config.json` | Renamed |
| `config/logging_config.yaml` | `pipeline/config/logging_config.yaml` | Same |
| `config/nozzlenet_config.yaml` | `models/nozzlenet/config/nozzlenet_config.yaml` | Moved |
| `csi/config/csi_config.yaml` | `models/csi/config/csi_config.yaml` | Moved |
| **NEW** | `pipeline/config/pipeline_config.yaml` | Main config |

### Service Files

| Legacy Service | New Service | Changes |
|----------------|-------------|---------|
| `bucher-gpio-setup.service` | `smartassist-gpio-export.service` | Renamed |
| `bucher-smart-sweeper-gpio-ignition-signal-monitor.service` | `smartassist-gpio-monitor.service` | Renamed |
| `bucher-can-init-250k.service` | `smartassist-can-init.service` | Renamed |
| `bucher-can-deinit.service` | `smartassist-can-deinit.service` | Renamed |
| `bucher-hourly-time-update.service` | `smartassist-time-sync.service` | Renamed |
| `bucher-d3-camera-init.service` | `smartassist-camera-init.service` | Renamed |
| `bucher-custom-video-test-launcher.service` | `smartassist-pipeline.service` | Renamed |
| **NEW** | `smartassist-can-server.service` | Extracted |
| **NEW** | `smartassist-health-monitor.service` | New feature |

### Script Files

| Legacy Script | New Script | Changes |
|---------------|------------|---------|
| `/usr/local/sbin/bucher/gpio_actions.sh` | `/opt/smartassist/services/gpio-monitor/src/monitor.sh` | Moved |
| `/usr/local/sbin/bucher/bucher-can-init.sh` | `/opt/smartassist/services/can-init/scripts/can-init.sh` | Moved |
| `/usr/local/sbin/bucher/initalise_bucher_d3_cameras_on_boot.py` | `/opt/smartassist/tools/initialize_cameras.py` | Moved |
| **NEW** | `/opt/smartassist/services/can-server/src/main.py` | Extracted |
| **NEW** | `/opt/smartassist/services/health-monitor/src/check_services.sh` | New |

---

## 🔄 Import Path Changes

### Legacy Imports
```python
# Old imports
from app_context import AppContext, Config
from utils import Configuration
import pipeline.csi.bins as csi_bins
from pipeline.can.state_machine import SmartStateMachine
```

### New Imports
```python
# New imports
from context import AppContext, Config
from utils.config import Configuration
from models.csi.src.bins import create_csiprobebin
from models.nozzlenet.src.state_machine import SmartStateMachine
from utils.paths import get_config_path, get_dbc_path
```

### Path Management

**Legacy:** Hardcoded paths
```python
config_path = '/mnt/ssd/csi_pipeline/config/logging_config.yaml'
dbc_path = '/mnt/ssd/csi_pipeline/dbc/TMS_V1_45_20251110.dbc'
```

**New:** Centralized path management
```python
from utils.paths import get_config_path, get_dbc_path

config_path = get_config_path('logging_config.yaml')
dbc_path = get_dbc_path('TMS_V1_45_20251110.dbc')
```

---

## 🔧 Configuration Changes

### Camera Configuration

**Legacy:** `bucher_camera_on_boot_config.json`
**New:** `camera_config.json`

**Changes:**
- Renamed file
- Moved to `pipeline/config/`
- Identical structure

### Logging Configuration

**No changes** - File stays the same

### Model Configurations

**Legacy:**
- `config/nozzlenet_config.yaml`
- `pipeline/csi/config/csi_config.yaml`

**New:**
- `models/nozzlenet/config/nozzlenet_config.yaml`
- `models/csi/config/csi_config.yaml`

**Changes:** Moved to model-specific directories

---

## 🚦 Service Changes

### Service Naming Convention

**Legacy:** `bucher-*`  
**New:** `smartassist-*`

**Consistency:** All services now use `smartassist-` prefix

### Service Scripts

**Legacy:** Scattered in `/usr/local/sbin/bucher/`  
**New:** Organized in `/opt/smartassist/services/*/src/` or `/opt/smartassist/services/*/scripts/`

### Service Functionality

**IMPORTANT:** All service functionality is IDENTICAL to legacy:

| Service | Type | Behavior | Changed? |
|---------|------|----------|----------|
| GPIO Export | oneshot | Exports GPIO PH.01 | ❌ No |
| GPIO Monitor | timer (5s) | Monitors IGNITION, triggers shutdown | ❌ No |
| CAN Init | oneshot | Initializes can0 at 250Kbps | ❌ No |
| Time Sync | oneshot (hourly timer) | Syncs time from GPS via CAN | ❌ No |
| Camera Init | oneshot | Detects and validates cameras | ❌ No |
| Pipeline | daemon (simple) | Main AI application | ❌ No |

**New Services:**
- `smartassist-can-server` - Extracted from pipeline (better isolation)
- `smartassist-health-monitor` - New monitoring feature

---

## 🔍 Functional Equivalence

### GStreamer Pipeline Topology

**IDENTICAL** - No changes to pipeline structure:

```
Legacy:
  nvarguscamerasrc (x4) → nvstreammux → tee → ...

New:
  nvarguscamerasrc (x4) → nvstreammux → tee → ...
  (exactly the same)
```

### AI Model Processing

**IDENTICAL** - Same inference logic:

**Nozzlenet:**
- Same detection classes
- Same state machine transitions
- Same fan speed control
- Same CAN message format

**CSI:**
- Same segmentation models
- Same trapezoid masking
- Same CSI calculation formula
- Same CSV output format

### CAN Communication

**IDENTICAL** - Same protocol:

**Messages sent:**
- 0x1F7 (nozzle status + fan speed)
- 0x0F7 (alternative message)

**Messages received:**
- 0x277 (override state)
- 0x284, 0x285, 0x384 (GPS data)

### State Machine Behavior

**IDENTICAL** - Same logic:

```python
# Legacy and New: Exact same state transitions
States: CLEAR → BLOCKED → CHECK → GRAVEL
Fan control: Same speed calculation
Status send: Same timing and logic
```

---

## 📊 Metrics Comparison

| Metric | Legacy | New | Improvement |
|--------|--------|-----|-------------|
| Main file size | 2000+ lines | ~150 lines | 93% reduction |
| Largest module | 2000 lines | ~600 lines | 70% smaller |
| Code reusability | Low (monolithic) | High (modular) | Significant |
| Test isolation | Difficult | Easy | Much better |
| Import complexity | Circular imports | Clean hierarchy | Cleaner |
| Path management | Hardcoded | Centralized | Better |
| Service organization | Scattered | Organized | Much better |

---

## 🎯 Migration Benefits

### For Developers

1. **Modularity:** Easier to understand and modify
2. **Testability:** Can test components in isolation
3. **Reusability:** Models can be reused in other projects
4. **Maintainability:** Smaller files, clearer structure
5. **Debugging:** Easier to locate issues

### For Deployment

1. **Portability:** Works from any installation location
2. **Service Management:** Clearer dependencies
3. **Monitoring:** Health check service
4. **Documentation:** Each component documented

### For Operations

1. **Health Monitoring:** Automated service checks
2. **Service Isolation:** CAN server can restart independently
3. **Path Flexibility:** Auto-detects installation location
4. **Logging:** Better organized logs

---

## ⚠️ Breaking Changes

### Import Paths

**If you have custom scripts importing pipeline code, update paths:**

```python
# Old
from app_context import AppContext
import utils

# New
from pipeline.src.context import AppContext
from pipeline.src.utils import config
```

### File Locations

**If scripts reference hardcoded file paths, use paths.py:**

```python
# Old
config = '/mnt/ssd/csi_pipeline/config/logging_config.yaml'

# New
from utils.paths import get_config_path
config = get_config_path('logging_config.yaml')
```

### Service Names

**systemctl commands need new names:**

```bash
# Old
sudo systemctl start bucher-custom-video-test-launcher

# New
sudo systemctl start smartassist-pipeline
```

---

## 🔄 Migration Checklist

If migrating an existing installation:

- [ ] Stop all legacy services
- [ ] Backup configuration files
- [ ] Backup any custom scripts
- [ ] Install new SmartAssist structure to `/opt/smartassist`
- [ ] Copy configuration customizations to new locations
- [ ] Update any custom scripts for new import paths
- [ ] Install new services with `install_services.sh`
- [ ] Disable old services
- [ ] Test new services one by one
- [ ] Validate full system with `validate_installation.py`
- [ ] Enable new services for auto-start
- [ ] Remove legacy installation (after validation)

---

## 📝 Summary

The restructuring from legacy to SmartAssist 2.0:

✅ **Improved:**
- Code organization (modular vs monolithic)
- File structure (logical grouping)
- Path management (centralized)
- Service naming (consistent)
- Documentation (comprehensive)
- Testability (isolated components)
- Maintainability (smaller files)

❌ **Unchanged:**
- All functionality (100% equivalent)
- GStreamer topology
- AI inference logic
- CAN protocol
- State machine behavior
- Configuration parameters
- Output formats

**Result:** Same functionality, better structure, easier to maintain.

---

**Migration completed:** December 13, 2025  
**Legacy preserved:** All functionality identical  
**Structure improved:** Modular, documented, testable