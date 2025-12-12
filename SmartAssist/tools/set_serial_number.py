#!/usr/bin/env python3
"""
Set Serial Number Script
Reads vehicle serial number from CAN bus and updates configuration

This script:
1. Listens to CAN message 0x205 for equipment number
2. Decodes serial number from DBC file
3. Updates logging_config.yaml with the serial number
4. Skips if serial number is already configured

USAGE:
    python3 set_serial_number.py [--can-interface can0] [--timeout 30]
    
EXIT CODES:
    0 - Serial number configured successfully
    1 - Error occurred
    2 - Serial number already configured (not an error)
"""

import argparse
import sys
import os
import time
from datetime import datetime
from pathlib import Path

# Try importing CAN libraries
try:
    import can
    import cantools
    HAS_CAN = True
except ImportError:
    HAS_CAN = False
    print("ERROR: python-can or cantools not installed")
    print("Install with: pip install python-can cantools")

# Try importing PyYAML
try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False
    print("ERROR: PyYAML not installed")
    print("Install with: pip install PyYAML")


def find_smartassist_root():
    """
    Find SmartAssist repository root
    
    Returns:
        Path: Path to repository root
    """
    # Check environment variable
    if 'SMARTASSIST_ROOT' in os.environ:
        return Path(os.environ['SMARTASSIST_ROOT'])
    
    # Try to find from current script location
    script_path = Path(__file__).resolve()
    
    # Look for smartassist repo markers
    current = script_path.parent
    while current != current.parent:
        if (current / 'pipeline' / 'config').exists():
            return current
        current = current.parent
    
    # Default fallback
    return Path('/opt/smartassist')


def get_config_path():
    """
    Get path to logging_config.yaml
    
    Returns:
        Path: Path to config file
    """
    root = find_smartassist_root()
    config_path = root / 'pipeline' / 'config' / 'logging_config.yaml'
    
    if not config_path.exists():
        # Try alternative location
        config_path = Path('/mnt/ssd/csi_pipeline/config/logging_config.yaml')
    
    return config_path


def get_dbc_path():
    """
    Get path to DBC file
    
    Returns:
        Path: Path to DBC file
    """
    root = find_smartassist_root()
    dbc_path = root / 'pipeline' / 'dbc' / 'TMS_V1_45_20251110.dbc'
    
    if not dbc_path.exists():
        # Try alternative location
        dbc_path = Path('/mnt/ssd/csi_pipeline/pipeline/dbc/TMS_V1_45_20251110.dbc')
    
    return dbc_path


def check_serial_configured(config_path):
    """
    Check if serial number is already configured
    
    Args:
        config_path: Path to logging_config.yaml
    
    Returns:
        tuple: (configured: bool, serial: str or None)
    """
    if not config_path.exists():
        return False, None
    
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        vehicle_info = config.get('vehicle_info', [])
        if vehicle_info and len(vehicle_info) > 0:
            serial = vehicle_info[0].get('serial_number', '')
            if serial and serial != 'UNKNOWN':
                return True, serial
        
        return False, None
    
    except Exception as e:
        print(f"Error reading config: {e}")
        return False, None


def read_serial_from_can(can_interface, timeout=30):
    """
    Read serial number from CAN bus
    
    Args:
        can_interface: CAN interface name (e.g., 'can0')
        timeout: Timeout in seconds
    
    Returns:
        str: Serial number or None if failed
    """
    print(f"Listening on {can_interface} for serial number (timeout: {timeout}s)...")
    
    try:
        # Load DBC file
        dbc_path = get_dbc_path()
        if not dbc_path.exists():
            print(f"ERROR: DBC file not found: {dbc_path}")
            return None
        
        print(f"Loading DBC file: {dbc_path}")
        db = cantools.database.load_file(str(dbc_path))
        
        # Open CAN bus
        bus = can.interface.Bus(channel=can_interface, bustype='socketcan')
        
        # Listen for message 0x205 (Equipment Number)
        start_time = time.time()
        
        while (time.time() - start_time) < timeout:
            msg = bus.recv(timeout=1.0)
            
            if msg is None:
                continue
            
            # Check if this is message 0x205
            if msg.arbitration_id == 0x205:
                print(f"Received message 0x205: {msg}")
                
                try:
                    # Decode message
                    decoded = db.decode_message(msg.arbitration_id, msg.data)
                    
                    # Look for equipment number field
                    # Field name may vary in DBC file
                    for key in ['EquipmentNumber', 'Equipment_Number', 'SerialNumber', 'Serial_Number']:
                        if key in decoded:
                            serial = str(decoded[key])
                            print(f"Found serial number: {serial}")
                            bus.shutdown()
                            return serial
                    
                    print(f"Decoded data: {decoded}")
                    print("WARNING: Equipment number field not found in decoded message")
                
                except Exception as e:
                    print(f"Error decoding message: {e}")
        
        print(f"Timeout: No serial number received after {timeout}s")
        bus.shutdown()
        return None
    
    except Exception as e:
        print(f"Error reading from CAN: {e}")
        return None


def update_config_serial(config_path, serial_number):
    """
    Update logging_config.yaml with serial number
    
    Args:
        config_path: Path to logging_config.yaml
        serial_number: Serial number to set
    
    Returns:
        bool: Success status
    """
    try:
        # Read existing config
        if config_path.exists():
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
        else:
            config = {}
        
        # Update serial number
        if 'vehicle_info' not in config:
            config['vehicle_info'] = [{}]
        
        config['vehicle_info'][0]['serial_number'] = serial_number
        
        # Write updated config
        with open(config_path, 'w') as f:
            yaml.dump(config, f, default_flow_style=False)
        
        print(f"✓ Serial number updated in config: {serial_number}")
        return True
    
    except Exception as e:
        print(f"ERROR: Failed to update config: {e}")
        return False


def main():
    """
    Main entry point
    
    Returns:
        int: Exit code
    """
    # Check dependencies
    if not HAS_CAN:
        print("ERROR: CAN libraries not available")
        return 1
    
    if not HAS_YAML:
        print("ERROR: PyYAML not available")
        return 1
    
    # Parse arguments
    parser = argparse.ArgumentParser(description='Set vehicle serial number from CAN bus')
    parser.add_argument('--can-interface', default='can0', help='CAN interface (default: can0)')
    parser.add_argument('--timeout', type=int, default=30, help='Timeout in seconds (default: 30)')
    parser.add_argument('--force', action='store_true', help='Update even if already configured')
    args = parser.parse_args()
    
    print("="*60)
    print("SmartAssist Serial Number Configuration")
    print("="*60)
    
    # Get config path
    config_path = get_config_path()
    print(f"\nConfig file: {config_path}")
    
    # Check if already configured
    if not args.force:
        configured, existing_serial = check_serial_configured(config_path)
        if configured:
            print(f"\n✓ Serial number already configured: {existing_serial}")
            print("Use --force to override")
            return 2  # Not an error, just already done
    
    # Read serial from CAN
    print(f"\nReading serial number from {args.can_interface}...")
    serial_number = read_serial_from_can(args.can_interface, args.timeout)
    
    if serial_number is None:
        print("\n✗ Failed to read serial number from CAN")
        return 1
    
    # Update config
    print(f"\nUpdating configuration with serial: {serial_number}")
    if update_config_serial(config_path, serial_number):
        print("\n✓ Serial number configuration complete!")
        return 0
    else:
        print("\n✗ Failed to update configuration")
        return 1


if __name__ == '__main__':
    sys.exit(main())