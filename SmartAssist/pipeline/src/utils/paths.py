"""
Path Management Utilities - FIXED VERSION
Auto-detects SmartAssist repository root and builds all paths relative to it
Works anywhere the repo is deployed (dev machine, edge device, CI/CD)

FIXES:
- Corrected CAN_DBC_DIR to point to pipeline/dbc/
- Added DBC_DIR as alias
- Validated all path construction
"""
import os


def get_repo_root():
    """
    Auto-detect SmartAssist repository root
    
    Priority:
    1. SMARTASSIST_ROOT environment variable (set by CI/CD)
    2. Auto-detect from this file's location (../../ from utils/)
    
    Returns:
        str: Absolute path to SmartAssist repo root
    """
    # Check environment variable first (CI/CD can override)
    if 'SMARTASSIST_ROOT' in os.environ:
        return os.environ['SMARTASSIST_ROOT']
    
    # Auto-detect: this file is at SmartAssist/pipeline/src/utils/paths.py
    # So repo root is 3 levels up
    this_file = os.path.abspath(__file__)
    utils_dir = os.path.dirname(this_file)      # .../pipeline/src/utils
    src_dir = os.path.dirname(utils_dir)        # .../pipeline/src
    pipeline_dir = os.path.dirname(src_dir)     # .../pipeline
    repo_root = os.path.dirname(pipeline_dir)   # .../SmartAssist
    
    return repo_root


# Repository root (auto-detected)
REPO_ROOT = get_repo_root()

# Pipeline paths
PIPELINE_ROOT = os.path.join(REPO_ROOT, "pipeline")
PIPELINE_SRC = os.path.join(PIPELINE_ROOT, "src")
PIPELINE_CONFIG = os.path.join(PIPELINE_ROOT, "config")
PIPELINE_DEEPSTREAM_CONFIGS = os.path.join(PIPELINE_ROOT, "deepstream_configs")

# DBC files location - FIXED!
DBC_DIR = os.path.join(PIPELINE_ROOT, "dbc")  # ← CORRECTED
CAN_DBC_DIR = DBC_DIR  # Alias for backward compatibility

# Model paths
MODELS_ROOT = os.path.join(REPO_ROOT, "models")

# CSI model
CSI_ROOT = os.path.join(MODELS_ROOT, "csi")
CSI_SRC = os.path.join(CSI_ROOT, "src")
CSI_WEIGHTS = os.path.join(CSI_ROOT, "weights/v1.0.0")
CSI_DEEPSTREAM_CONFIGS = os.path.join(CSI_ROOT, "deepstream_configs")

CSI_ROAD_CONFIG = os.path.join(CSI_DEEPSTREAM_CONFIGS, "road_config.txt")
CSI_GARBAGE_CONFIG = os.path.join(CSI_DEEPSTREAM_CONFIGS, "garbage_config.txt")

# Nozzlenet model
NOZZLENET_ROOT = os.path.join(MODELS_ROOT, "nozzlenet")
NOZZLENET_SRC = os.path.join(NOZZLENET_ROOT, "src")
NOZZLENET_WEIGHTS = os.path.join(NOZZLENET_ROOT, "weights/v2.5.3")
NOZZLENET_DEEPSTREAM_CONFIGS = os.path.join(NOZZLENET_ROOT, "deepstream_configs")

# Shared config paths
CONFIG_ROOT = os.path.join(REPO_ROOT, "config")

# Output paths (external - not in repo)
OUTPUT_ROOT = "/mnt/syslogic_sd_card/upload"
CSV_OUTPUT_DIR = os.path.join(OUTPUT_ROOT, "csv")
VIDEO_OUTPUT_DIR = os.path.join(OUTPUT_ROOT, "video")

# Tools directory
TOOLS_DIR = os.path.join(REPO_ROOT, "tools")

CAN_LOG_DIR = os.path.join(OUTPUT_ROOT, "can_logs")
def get_model_path(model_name, version, filename):
    """
    Get path to model weight file
    
    Args:
        model_name: 'csi' or 'nozzlenet'
        version: Version string (e.g., 'v1.0.0', 'v2.5.3')
        filename: Model filename (e.g., 'model.plan', 'road_segmentation.onnx')
    
    Returns:
        str: Absolute path to model file
    """
    if model_name == 'csi':
        return os.path.join(CSI_ROOT, f"weights/{version}/{filename}")
    elif model_name == 'nozzlenet':
        return os.path.join(NOZZLENET_ROOT, f"weights/{version}/{filename}")
    else:
        raise ValueError(f"Unknown model: {model_name}")


def get_dbc_path(dbc_filename):
    """
    Get path to DBC file
    
    Args:
        dbc_filename: DBC filename (e.g., 'TMS_V1_45_20251110.dbc')
    
    Returns:
        str: Absolute path to DBC file
    """
    return os.path.join(DBC_DIR, dbc_filename)  # ← FIXED to use DBC_DIR


def get_config_path(config_filename):
    """
    Get path to pipeline config file
    
    Args:
        config_filename: Config filename (e.g., 'pipeline_config.yaml')
    
    Returns:
        str: Absolute path to config file
    """
    return os.path.join(PIPELINE_CONFIG, config_filename)


def get_deepstream_config_path(model_name, config_filename):
    """
    Get path to DeepStream config file
    
    Args:
        model_name: 'pipeline', 'csi', or 'nozzlenet'
        config_filename: Config filename (e.g., 'infer_config.txt')
    
    Returns:
        str: Absolute path to DeepStream config file
    """
    if model_name == 'pipeline':
        return os.path.join(PIPELINE_DEEPSTREAM_CONFIGS, config_filename)
    elif model_name == 'csi':
        return os.path.join(CSI_DEEPSTREAM_CONFIGS, config_filename)
    elif model_name == 'nozzlenet':
        return os.path.join(NOZZLENET_DEEPSTREAM_CONFIGS, config_filename)
    else:
        raise ValueError(f"Unknown model: {model_name}")


# Print paths on import (useful for debugging)
if __name__ == "__main__":
    print("SmartAssist Path Configuration (FIXED VERSION)")
    print("=" * 60)
    print(f"Repository Root: {REPO_ROOT}")
    print(f"Pipeline Root:   {PIPELINE_ROOT}")
    print(f"Models Root:     {MODELS_ROOT}")
    print(f"CSI Root:        {CSI_ROOT}")
    print(f"Nozzlenet Root:  {NOZZLENET_ROOT}")
    print(f"Config Root:     {CONFIG_ROOT}")
    print(f"DBC Dir:         {DBC_DIR}")  # ← FIXED
    print(f"CAN DBC Dir:     {CAN_DBC_DIR}")
    print(f"Tools Dir:       {TOOLS_DIR}")
    print(f"CSV Output:      {CSV_OUTPUT_DIR}")
    print("=" * 60)