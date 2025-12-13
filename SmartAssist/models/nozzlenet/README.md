
# Nozzlenet Model Documentation

## Nozzle Detection

**Detection Classes:**
- CLEAR (0): Nozzle clear, no blockage
- BLOCKED (1): Nozzle blocked
- CHECK (2): Nozzle needs inspection
- GRAVEL (3): Gravel detected

## State Machine

**States:**
```
CLEAR → BLOCKED → CHECK → GRAVEL
  ↑        ↓
  └────────┘ (can return to CLEAR)
```

**Transitions:**
- Based on detection confidence
- Hysteresis to prevent flickering
- Configurable thresholds

## Fan Speed Control

**Calculation:**
```python
if nozzle_state == CLEAR:
    fan_speed = 100
elif nozzle_state == BLOCKED:
    fan_speed = 150
elif nozzle_state == CHECK:
    fan_speed = 125
else:  # GRAVEL
    fan_speed = 0
```

## CAN Output

**Message 0x1F7:**
- Byte 0-1: Nozzle status
- Byte 2-3: Fan speed
- Sent every 100ms

## Configuration

**File:** `config/nozzlenet_config.yaml`
**DeepStream:** `deepstream_configs/infer_config.txt`