#!/usr/bin/env python3
"""
Camera Initialization Script
Detects and validates CSI cameras on boot

Location: SmartAssist/tools/initialize_cameras.py
Usage: python3 initialize_cameras.py
"""
import os
import sys
import json
import subprocess
from datetime import datetime

def detect_cameras():
    """Detect available V4L2 cameras"""
    print('Detecting cameras...')
    cameras = []
    
    try:
        result = subprocess.run(
            ['v4l2-ctl', '--list-devices'],
            capture_output=True,
            text=True,
            check=True
        )
        
        lines = result.stdout.split('\n')
        current_device = None
        
        for line in lines:
            if 'vi-output' in line:
                current_device = line.split('(')[0].strip()
            elif line.strip().startswith('/dev/video'):
                video_node = line.strip()
                sensor_id = int(video_node.replace('/dev/video', ''))
                cameras.append({
                    'device': current_device,
                    'video_node': video_node,
                    'sensor_id': sensor_id
                })
        
        print(f'Found {len(cameras)} cameras')
        return cameras
    
    except Exception as e:
        print(f'Failed to detect cameras: {e}')
        return []

def test_camera(video_node):
    """Test if camera can capture frames"""
    print(f'Testing {video_node}...')
    
    try:
        result = subprocess.run(
            [
                'v4l2-ctl',
                '-d', video_node,
                '--set-fmt-video=width=1920,height=1080',
                '--stream-mmap',
                '--stream-count=1'
            ],
            capture_output=True,
            timeout=10,
            check=True
        )
        print(f'  ✓ {video_node} OK')
        return True
    except:
        print(f'  ✗ {video_node} FAILED')
        return False

def main():
    print('=' * 60)
    print('SmartAssist Camera Initialization')
    print('=' * 60)
    
    cameras = detect_cameras()
    
    if not cameras:
        print('\n✗ No cameras detected')
        return 1
    
    print('\nTesting cameras...')
    success_count = 0
    
    for cam in cameras:
        if test_camera(cam['video_node']):
            success_count += 1
    
    # Export status
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    status_file = f'/tmp/camera_init_results_{timestamp}.json'
    
    status = {
        'timestamp': datetime.now().isoformat(),
        'success': success_count > 0,
        'cameras_detected': len(cameras),
        'cameras_working': success_count
    }
    
    with open(status_file, 'w') as f:
        json.dump(status, f, indent=2)
    
    print(f'\nSummary: {success_count}/{len(cameras)} cameras working')
    print(f'Status exported to: {status_file}')
    
    if success_count > 0:
        print('\n✓ Camera initialization successful')
        return 0
    else:
        print('\n✗ Camera initialization failed')
        return 1

if __name__ == '__main__':
    sys.exit(main())