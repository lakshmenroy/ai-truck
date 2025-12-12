#!/usr/bin/env python3
"""
Camera Initialization Script
Detects and validates all CSI cameras at system boot

This script:
1. Detects all V4L2 video devices
2. Tests each camera by attempting to capture a frame
3. Exports initialization status to JSON file
4. Returns appropriate exit code for systemd service

Output: /tmp/camera_init_results_YYYYMMDDHHMM.json

USAGE:
    python3 initialize_cameras.py
    
EXIT CODES:
    0 - All cameras initialized successfully
    1 - One or more cameras failed to initialize
"""

import os
import sys
import json
import subprocess
from datetime import datetime
from pathlib import Path

# Try importing cv2, fallback to subprocess if not available
try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False
    print("WARNING: OpenCV not available, using v4l2-ctl for testing")


def get_video_devices():
    """
    Get list of all video devices
    
    Returns:
        list: List of video device paths (e.g., ['/dev/video0', '/dev/video1'])
    """
    devices = []
    for i in range(10):  # Check up to 10 video devices
        device = f'/dev/video{i}'
        if os.path.exists(device):
            devices.append(device)
    return devices


def test_camera_v4l2(device):
    """
    Test camera using v4l2-ctl command
    
    Args:
        device: Device path (e.g., '/dev/video0')
    
    Returns:
        tuple: (success: bool, info: dict)
    """
    try:
        # Query device capabilities
        result = subprocess.run(
            ['v4l2-ctl', '--device', device, '--all'],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0:
            # Parse device info from output
            output = result.stdout
            
            # Extract driver name
            driver = "unknown"
            for line in output.split('\n'):
                if 'Driver name' in line:
                    driver = line.split(':')[-1].strip()
                    break
            
            return True, {
                'device': device,
                'driver': driver,
                'method': 'v4l2-ctl'
            }
        else:
            return False, {
                'device': device,
                'error': 'v4l2-ctl failed',
                'method': 'v4l2-ctl'
            }
    
    except subprocess.TimeoutExpired:
        return False, {
            'device': device,
            'error': 'timeout',
            'method': 'v4l2-ctl'
        }
    except Exception as e:
        return False, {
            'device': device,
            'error': str(e),
            'method': 'v4l2-ctl'
        }


def test_camera_opencv(device):
    """
    Test camera using OpenCV
    
    Args:
        device: Device path (e.g., '/dev/video0')
    
    Returns:
        tuple: (success: bool, info: dict)
    """
    try:
        # Extract device number
        device_num = int(device.replace('/dev/video', ''))
        
        # Try to open camera
        cap = cv2.VideoCapture(device_num)
        
        if not cap.isOpened():
            return False, {
                'device': device,
                'error': 'Failed to open device',
                'method': 'opencv'
            }
        
        # Try to capture a frame
        ret, frame = cap.read()
        cap.release()
        
        if ret and frame is not None:
            height, width = frame.shape[:2]
            return True, {
                'device': device,
                'resolution': f'{width}x{height}',
                'method': 'opencv'
            }
        else:
            return False, {
                'device': device,
                'error': 'Failed to capture frame',
                'method': 'opencv'
            }
    
    except Exception as e:
        return False, {
            'device': device,
            'error': str(e),
            'method': 'opencv'
        }


def initialize_cameras():
    """
    Initialize and test all cameras
    
    Returns:
        dict: Initialization results
    """
    print("="*60)
    print("Camera Initialization")
    print("="*60)
    
    # Get all video devices
    devices = get_video_devices()
    print(f"\nDetected {len(devices)} video devices: {devices}")
    
    if not devices:
        print("ERROR: No video devices found!")
        return {
            'success': False,
            'cameras_detected': 0,
            'cameras_working': 0,
            'cameras': [],
            'error': 'No video devices found'
        }
    
    # Test each camera
    cameras = []
    working_count = 0
    
    for device in devices:
        print(f"\nTesting {device}...")
        
        # Try OpenCV first if available
        if HAS_CV2:
            success, info = test_camera_opencv(device)
        else:
            success, info = test_camera_v4l2(device)
        
        if success:
            print(f"  ✓ {device} OK")
            working_count += 1
        else:
            print(f"  ✗ {device} FAILED: {info.get('error', 'Unknown error')}")
        
        cameras.append({
            'device': device,
            'success': success,
            'info': info
        })
    
    # Prepare results
    all_success = (working_count == len(devices))
    
    results = {
        'success': all_success,
        'timestamp': datetime.now().isoformat(),
        'cameras_detected': len(devices),
        'cameras_working': working_count,
        'cameras': cameras
    }
    
    print("\n" + "="*60)
    print(f"Cameras working: {working_count}/{len(devices)}")
    print("="*60)
    
    return results


def export_results(results):
    """
    Export initialization results to JSON file
    
    Args:
        results: Results dictionary
    
    Returns:
        str: Output file path
    """
    # Create output filename with timestamp
    timestamp = datetime.now().strftime('%Y%m%d%H%M')
    output_file = f'/tmp/camera_init_results_{timestamp}.json'
    
    # Write JSON
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\nResults exported to: {output_file}")
    
    return output_file


def main():
    """
    Main entry point
    
    Returns:
        int: Exit code (0 = success, 1 = failure)
    """
    try:
        # Initialize cameras
        results = initialize_cameras()
        
        # Export results
        export_results(results)
        
        # Return appropriate exit code
        if results['success']:
            print("\n✓ Camera initialization successful!")
            return 0
        else:
            print("\n✗ Camera initialization failed!")
            return 1
    
    except Exception as e:
        print(f"\nFATAL ERROR: {e}", file=sys.stderr)
        
        # Try to export error results
        try:
            error_results = {
                'success': False,
                'timestamp': datetime.now().isoformat(),
                'error': str(e),
                'cameras_detected': 0,
                'cameras_working': 0,
                'cameras': []
            }
            export_results(error_results)
        except:
            pass
        
        return 1


if __name__ == '__main__':
    sys.exit(main())