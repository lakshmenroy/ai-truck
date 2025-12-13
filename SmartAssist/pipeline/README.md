# Pipeline Architecture

## Overview

The SmartAssist pipeline is a GStreamer-based application that processes 4 camera feeds simultaneously for nozzle detection and clean street index calculation.

## Directory Structure

```
pipeline/
├── src/              # Source code
│   ├── main.py       # Entry point
│   ├── context.py    # Configuration
│   ├── pipeline/     # GStreamer components
│   ├── can/          # CAN client
│   ├── monitoring/   # FPS/override monitoring
│   └── utils/        # Helpers
├── config/           # Configuration files
├── dbc/              # CAN database files
└── systemd/          # Service file
```

## GStreamer Topology

```
[Camera 0-3] nvarguscamerasrc
     ↓
nvvideoconvert
     ↓
tee (3-way split)
├─→ HR Output (H.265 recording)
├─→ nvstreamdemux → Per-camera processing
│   ├─→ Nozzle cameras → Inference
│   └─→ CSI cameras → Segmentation
└─→ nvdsmetamux → OSD → UDP
```

## Configuration

**Main config:** `config/pipeline_config.yaml`

**Camera config:** `config/camera_config.json`

**Logging config:** `config/logging_config.yaml`

## Key Components

- **main.py**: Application entry point
- **builder.py**: Pipeline construction
- **bins.py**: Bin creation functions
- **probes**: Buffer processing (in models/)