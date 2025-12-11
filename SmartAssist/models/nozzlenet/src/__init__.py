"""
Nozzlenet Model Module
Nozzle detection and state management for SmartAssist system

This module provides:
- Detection constants (class IDs, states, colors)
- State machine (SmartStateMachine for nozzle control)
- Bin creation (create_nozzlenet_inference_bin)
- Buffer probe (nozzlenet_src_pad_buffer_probe)

MODULAR STRUCTURE: All nozzlenet logic is self-contained in this module
for traceability and version management.
"""

# Constants
from .constants import (
    NOZZLENET_UNIQUE_ID,
    PGIE_CLASS_ID_BACKGROUND,
    PGIE_CLASS_ID_ACTION_OBJECT,
    PGIE_CLASS_ID_CHECK_NOZZLE,
    PGIE_CLASS_ID_GRAVEL,
    PGIE_CLASS_ID_NOZZLE_BLOCKED,
    PGIE_CLASS_ID_NOZZLE_CLEAR,
    NOZZLE_STATUS_CLEAR,
    NOZZLE_STATUS_BLOCKED,
    NOZZLE_STATUS_CHECK,
    NOZZLE_STATUS_GRAVEL,
    STATE_IDLE,
    STATE_NOZZLE_CLEAR,
    STATE_NOZZLE_BLOCKED,
    STATE_NOZZLE_CHECK,
    STATE_GRAVEL_DETECTED,
    NOZZLE_STATE_IDLE,
    NOZZLE_STATE_CLEAR,
    NOZZLE_STATE_BLOCKED,
    NOZZLE_STATE_CHECK,
    NOZZLE_STATE_GRAVEL,
    FAN_SPEED_OFF,
    FAN_SPEED_LOW,
    FAN_SPEED_MEDIUM,
    FAN_SPEED_HIGH,
    BORDER_COLOR_CLEAR,
    BORDER_COLOR_BLOCKED,
    BORDER_COLOR_CHECK,
    BORDER_COLOR_GRAVEL,
    BORDER_COLOR_ACTION_OBJECT,
    BORDER_WIDTH,
    NOZZLE_CAMERAS
)

# State machine
from .state_machine import SmartStateMachine

# Bin creation - REAL function
from .bins import (
    create_nozzlenet_inference_bin,
    get_nozzlenet_config_defaults,
    get_nozzlenet_cameras
)

# Buffer probe - REAL function
from .probes import nozzlenet_src_pad_buffer_probe

__all__ = [
    # Constants
    'NOZZLENET_UNIQUE_ID',
    'PGIE_CLASS_ID_BACKGROUND',
    'PGIE_CLASS_ID_ACTION_OBJECT',
    'PGIE_CLASS_ID_CHECK_NOZZLE',
    'PGIE_CLASS_ID_GRAVEL',
    'PGIE_CLASS_ID_NOZZLE_BLOCKED',
    'PGIE_CLASS_ID_NOZZLE_CLEAR',
    'NOZZLE_STATUS_CLEAR',
    'NOZZLE_STATUS_BLOCKED',
    'NOZZLE_STATUS_CHECK',
    'NOZZLE_STATUS_GRAVEL',
    'STATE_IDLE',
    'STATE_NOZZLE_CLEAR',
    'STATE_NOZZLE_BLOCKED',
    'STATE_NOZZLE_CHECK',
    'STATE_GRAVEL_DETECTED',
    'NOZZLE_STATE_IDLE',
    'NOZZLE_STATE_CLEAR',
    'NOZZLE_STATE_BLOCKED',
    'NOZZLE_STATE_CHECK',
    'NOZZLE_STATE_GRAVEL',
    'FAN_SPEED_OFF',
    'FAN_SPEED_LOW',
    'FAN_SPEED_MEDIUM',
    'FAN_SPEED_HIGH',
    'BORDER_COLOR_CLEAR',
    'BORDER_COLOR_BLOCKED',
    'BORDER_COLOR_CHECK',
    'BORDER_COLOR_GRAVEL',
    'BORDER_COLOR_ACTION_OBJECT',
    'BORDER_WIDTH',
    'NOZZLE_CAMERAS',
    
    # State machine
    'SmartStateMachine',
    
    # Bin creation - REAL function
    'create_nozzlenet_inference_bin',
    'get_nozzlenet_config_defaults',
    'get_nozzlenet_cameras',
    
    # Buffer probe - REAL function
    'nozzlenet_src_pad_buffer_probe',
]