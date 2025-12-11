"""
Nozzlenet Model Constants
Detection categories and state definitions for nozzle monitoring

VERIFIED: Values from original detection_categories.py
"""

# Nozzlenet unique ID for DeepStream
NOZZLENET_UNIQUE_ID = 1

# Detection class IDs - VERIFIED from original
PGIE_CLASS_ID_BACKGROUND = 0
PGIE_CLASS_ID_ACTION_OBJECT = 1
PGIE_CLASS_ID_CHECK_NOZZLE = 2
PGIE_CLASS_ID_GRAVEL = 3
PGIE_CLASS_ID_NOZZLE_BLOCKED = 4
PGIE_CLASS_ID_NOZZLE_CLEAR = 5

# Detection status strings - VERIFIED
NOZZLE_STATUS_CLEAR = 'clear'
NOZZLE_STATUS_BLOCKED = 'blocked'
NOZZLE_STATUS_CHECK = 'check'
NOZZLE_STATUS_GRAVEL = 'gravel'

# State machine states - VERIFIED
STATE_IDLE = 'IDLE'
STATE_NOZZLE_CLEAR = 'NOZZLE_CLEAR'
STATE_NOZZLE_BLOCKED = 'NOZZLE_BLOCKED'
STATE_NOZZLE_CHECK = 'NOZZLE_CHECK'
STATE_GRAVEL_DETECTED = 'GRAVEL_DETECTED'

# Nozzle state values for CAN - VERIFIED
NOZZLE_STATE_IDLE = 0
NOZZLE_STATE_CLEAR = 1
NOZZLE_STATE_BLOCKED = 2
NOZZLE_STATE_CHECK = 3
NOZZLE_STATE_GRAVEL = 4

# Fan speed values - VERIFIED from state machine
FAN_SPEED_OFF = 0
FAN_SPEED_LOW = 2    # Clear state
FAN_SPEED_MEDIUM = 5  # Check state
FAN_SPEED_HIGH = 8    # Blocked state

# Detection border colors (RGBA) - VERIFIED exact values
BORDER_COLOR_CLEAR = (0.1411, 0.8019, 0.3254, 0.9)      # Green
BORDER_COLOR_BLOCKED = (1.0, 0.3764, 0.2156, 0.9)       # Red
BORDER_COLOR_CHECK = (0.96078431, 0.57647059, 0.19215686, 0.9)  # Orange
BORDER_COLOR_GRAVEL = (0.678, 0.847, 0.902, 0.9)        # Light Blue
BORDER_COLOR_ACTION_OBJECT = (1.0, 0.0, 0.48627451, 0.9)  # Pink

# Border width
BORDER_WIDTH = 5

# Camera mapping - VERIFIED
NOZZLE_CAMERAS = ['right', 'left']  # primary_nozzle, secondary_nozzle