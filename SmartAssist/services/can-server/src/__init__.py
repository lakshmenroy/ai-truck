"""
SmartAssist CAN Server Module
Standalone service for CAN bus communication

This module provides the CANServer class for managing:
- CAN bus monitoring (can0, can1)
- Client connections via Unix socket
- CAN message sending (0x0F7 errors, 0x1F7 status)
- FPS and camera monitoring
- Data logging

Usage:
    python -m services.can-server.src.main

Or as a systemd service:
    systemctl start smartassist-can-server
"""
from .main import CANServer, main

__all__ = ['CANServer', 'main']
__version__ = '1.0.0'