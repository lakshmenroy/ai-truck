
# Models Architecture

## Overview

AI models are organized in independent modules with their own configurations and DeepStream settings.

## Structure

```
models/
├── csi/              # Clean Street Index
│   ├── src/          # CSI-specific code
│   ├── config/       # CSI parameters
│   ├── deepstream_configs/
│   └── Weights/
└── nozzlenet/        # Nozzle detection
    ├── src/          # Nozzlenet code
    ├── config/       # Nozzlenet parameters
    ├── deepstream_configs/
    └── Weights/
```

## CSI Model

**Purpose:** Calculate cleanliness index from road/garbage segmentation

**Components:**
- Road segmentation model
- Garbage detection model
- Trapezoid ROI masking
- CSI calculation algorithm

**Location:** `models/csi/`

## Nozzlenet Model

**Purpose:** Detect nozzle status and control fan speed

**Components:**
- Object detection model
- State machine
- Fan speed controller
- CAN message generator

**Location:** `models/nozzlenet/`

## Adding New Models

1. Create directory in `models/your_model/`
2. Add `src/` with bins.py and probes.py
3. Add `config/` with YAML configuration
4. Add `deepstream_configs/` with inference configs
5. Import in pipeline builder