#!/usr/bin/env python3
"""
SmartAssist Time Synchronization Service
Synchronizes system time from GPS timestamp on CAN bus

Listens to CAN messages for GPS time and sets system time accordingly.
Fallback: If no GPS time available, sets time to last known time + 1 minute.

Usage: python3 can_time_sync.py
Exit codes: 0 = success, 1 = error
"""

import os
import sys
import time
import subprocess
from datetime import datetime, timedelta
import can
import cantools
import logging

# Configuration
CAN_INTERFACE = 'can0'
DBC_FILE = '/opt/smartassist/pipeline/dbc/TMS_V1_45_20251110.dbc'
TIME_MESSAGE_NAME = 'GPS_Time'  # Update with actual message name from DBC
TIME_SIGNAL_NAME = 'timestamp'  # Update with actual signal name
FALLBACK_TIME_FILE = '/var/lib/smartassist/last_known_time.txt'
CHECK_INTERVAL = 30  # Check for time every 30 seconds
TIMEOUT = 300  # 5 minutes timeout for GPS time

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(message)s'
)
logger = logging.getLogger('time-sync')


def set_system_time(timestamp):
    """
    Set system time using datetime timestamp
    
    Args:
        timestamp: datetime object
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Format: YYYY-MM-DD HH:MM:SS
        time_str = timestamp.strftime('%Y-%m-%d %H:%M:%S')
        
        # Use timedatectl to set time
        cmd = ['sudo', 'timedatectl', 'set-time', time_str]
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            logger.info(f'System time set to: {time_str}')
            return True
        else:
            logger.error(f'Failed to set time: {result.stderr}')
            return False
            
    except Exception as e:
        logger.error(f'Error setting system time: {e}')
        return False


def save_last_known_time():
    """Save current time to fallback file"""
    try:
        os.makedirs(os.path.dirname(FALLBACK_TIME_FILE), exist_ok=True)
        with open(FALLBACK_TIME_FILE, 'w') as f:
            f.write(datetime.now().isoformat())
        logger.debug(f'Saved last known time to {FALLBACK_TIME_FILE}')
    except Exception as e:
        logger.error(f'Failed to save last known time: {e}')


def load_last_known_time():
    """Load last known time from fallback file"""
    try:
        if os.path.exists(FALLBACK_TIME_FILE):
            with open(FALLBACK_TIME_FILE, 'r') as f:
                time_str = f.read().strip()
                last_time = datetime.fromisoformat(time_str)
                logger.info(f'Loaded last known time: {last_time}')
                return last_time
    except Exception as e:
        logger.error(f'Failed to load last known time: {e}')
    
    return None


def set_fallback_time():
    """
    Set time to last known time + 1 minute as fallback
    
    Returns:
        bool: True if successful, False otherwise
    """
    logger.warning('No GPS time available, using fallback time')
    
    last_time = load_last_known_time()
    
    if last_time:
        # Add 1 minute to last known time
        fallback_time = last_time + timedelta(minutes=1)
        logger.info(f'Setting fallback time: {fallback_time}')
        return set_system_time(fallback_time)
    else:
        logger.error('No last known time available, cannot set fallback')
        return False


def listen_for_gps_time():
    """
    Listen to CAN bus for GPS time messages
    
    Returns:
        datetime or None: GPS timestamp if found, None otherwise
    """
    try:
        # Load DBC file
        logger.info(f'Loading DBC file: {DBC_FILE}')
        db = cantools.database.load_file(DBC_FILE)
        
        # Get time message definition
        try:
            time_message = db.get_message_by_name(TIME_MESSAGE_NAME)
            logger.info(f'Listening for {TIME_MESSAGE_NAME} on {CAN_INTERFACE}')
        except KeyError:
            logger.error(f'Message {TIME_MESSAGE_NAME} not found in DBC')
            logger.info('Available messages:')
            for msg in db.messages:
                logger.info(f'  - {msg.name} (0x{msg.frame_id:X})')
            return None
        
        # Create CAN bus interface
        bus = can.interface.Bus(channel=CAN_INTERFACE, bustype='socketcan')
        
        # Listen for messages with timeout
        start_time = time.time()
        
        while time.time() - start_time < TIMEOUT:
            message = bus.recv(timeout=1.0)
            
            if message is None:
                continue
            
            # Check if this is the time message
            if message.arbitration_id == time_message.frame_id:
                # Decode message
                try:
                    data = db.decode_message(message.arbitration_id, message.data)
                    
                    # Extract timestamp signal
                    if TIME_SIGNAL_NAME in data:
                        timestamp_value = data[TIME_SIGNAL_NAME]
                        
                        # Convert to datetime (adjust based on DBC signal format)
                        # Common formats: Unix timestamp, GPS week/second, etc.
                        # TODO: Update conversion based on actual DBC signal format
                        
                        if isinstance(timestamp_value, (int, float)):
                            # Assume Unix timestamp
                            gps_time = datetime.fromtimestamp(timestamp_value)
                            logger.info(f'GPS time received: {gps_time}')
                            return gps_time
                        else:
                            logger.warning(f'Unexpected timestamp format: {type(timestamp_value)}')
                    else:
                        logger.warning(f'Signal {TIME_SIGNAL_NAME} not found in message')
                        logger.debug(f'Available signals: {list(data.keys())}')
                        
                except Exception as e:
                    logger.error(f'Error decoding message: {e}')
        
        logger.warning(f'Timeout: No GPS time received in {TIMEOUT} seconds')
        return None
        
    except FileNotFoundError:
        logger.error(f'DBC file not found: {DBC_FILE}')
        return None
    except Exception as e:
        logger.error(f'Error listening for GPS time: {e}')
        return None


def main():
    """Main time sync function"""
    logger.info('SmartAssist Time Sync starting...')
    
    # Try to get GPS time from CAN
    gps_time = listen_for_gps_time()
    
    if gps_time:
        # Set system time from GPS
        if set_system_time(gps_time):
            save_last_known_time()
            logger.info('Time synchronized from GPS successfully')
            return 0
        else:
            logger.error('Failed to set time from GPS')
    
    # Fallback to last known time + 1 minute
    if set_fallback_time():
        logger.info('Time set using fallback method')
        return 0
    else:
        logger.error('Failed to set time using fallback method')
        return 1


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        logger.info('Interrupted by user')
        sys.exit(0)
    except Exception as e:
        logger.error(f'Unexpected error: {e}')
        sys.exit(1)
