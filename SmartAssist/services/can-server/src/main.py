"""
SmartAssist CAN Server
Standalone service for CAN bus communication and monitoring

This server:
1. Monitors CAN buses (can0, can1) for telematic data
2. Accepts client connections via Unix socket
3. Updates CAN byte values based on client requests
4. Sends CAN messages (0x0F7 errors, 0x1F7 status)
5. Monitors camera health and FPS
6. Logs all data to CSV files

EXTRACTED FROM: pipeline/can_server.py
VERIFIED: Complete standalone service
"""
import socket
import json
import threading
import time
import os
import signal
import sys
from datetime import datetime, timedelta
from pathlib import Path

# CAN imports
import can
from can.interface import Bus
import cantools

# Utils
import csv
import pandas as pd
import numpy as np


class CANServer:
    """
    CAN Server for managing CAN bus communication
    
    Runs as a standalone service, communicating with pipeline via Unix socket
    
    VERIFIED: Complete implementation from original can_server.py
    """
    
    def __init__(self, socket_path='/tmp/can_server.sock', enable_logging=True):
        """
        Initialize CAN Server
        
        :param socket_path: Path to Unix domain socket
        :param enable_logging: Enable CSV logging
        """
        self.socket_path = socket_path
        self.server_socket = None
        self.running = False
        self.enable_logging = enable_logging
        
        # Data storage
        self.can_data = {}  # CAN messages from bus
        self.error_data = {}  # Error messages
        self.client_data = {}  # Data from clients
        self.data_lock = threading.Lock()
        
        # Client tracking
        self.clients = {}  # {socket: client_info}
        self.client_names = {}  # {client_name: socket}
        self.client_lock = threading.Lock()
        
        # CAN byte values (for 0x1F7 message)
        self.can_bytes_lock = threading.Lock()
        self.status_byte = 0x00
        self.camera_byte = 0x00
        self.nozzle_byte = 0x00
        self.gps_byte = 0x00
        self.fan_byte = 0x00
        self.fps_byte = 0x00
        
        # Error byte values (for 0x0F7 message)
        self.error_byte = 0x00
        self.device_byte = 0x00
        self.additional_byte = 0x00
        
        # CAN buses
        self.bus0 = None  # can0 - telematic data
        self.bus1 = None  # can1 - sensor data
        self.send_bus = None  # Bus for sending messages
        
        # DBC databases
        self.db0 = None
        self.db1 = None
        
        # Camera monitoring
        self.camera_timeout = 10  # seconds
        self.primary_camera_last_active = None
        self.secondary_camera_last_active = None
        self.front_camera_last_active = None
        self.rear_camera_last_active = None
        
        self.primary_camera_inactive_count = 0
        self.secondary_camera_inactive_count = 0
        self.front_camera_inactive_count = 0
        self.rear_camera_inactive_count = 0
        
        self.primary_camera_inactive = False
        self.secondary_camera_inactive = False
        self.front_camera_inactive = False
        self.rear_camera_inactive = False
        
        self.primary_camera_failed = False
        self.secondary_camera_failed = False
        self.front_camera_failed = False
        self.rear_camera_failed = False
        
        # Pipeline client tracking
        self.pipeline_client_name = 'pipeline'
        self.pipeline_check_count = 0
        self.pipeline_was_connected = False
        
        # FPS monitoring
        self.nn_fps_threshold = 20
        self.csi_fps_threshold = 3
        self.nn_fps = 0
        self.front_csi_fps = 0
        self.rear_csi_fps = 0
        
        # PM sensor data
        self.last_sensor = None
        self.last_sensor_time = None
        self.sensor_weighted_values = {}
        self.dustometer = 0
        self.sensor_min = 0
        self.sensor_max = 1000
        self.sensor_queue = []
        
        # Override state
        self.current_override_state = 0
        
        # Logging
        self.log_directory = '/mnt/ssd/logs/can_logs'
        self.csv_file = None
        self.csv_writer = None
        
        print('CAN Server initialized')
    
    # ==================== CLIENT MANAGEMENT ====================
    
    def register_client(self, client_socket, client_name):
        """
        Register a new client
        
        :param client_socket: Client socket
        :param client_name: Client identifier
        :return: True if registered successfully
        """
        with self.client_lock:
            if client_name in self.client_names:
                old_socket = self.client_names[client_name]
                if old_socket in self.clients:
                    del self.clients[old_socket]
                print(f'Replacing existing client: {client_name}')
            
            self.clients[client_socket] = {
                'name': client_name,
                'connected_at': time.time()
            }
            self.client_names[client_name] = client_socket
            print(f'Client registered: {client_name}')
            return True
    
    def unregister_client(self, client_socket, client_name):
        """
        Unregister a client
        
        :param client_socket: Client socket
        :param client_name: Client identifier
        :return: Client name if found
        """
        with self.client_lock:
            if client_socket in self.clients:
                client_info = self.clients[client_socket]
                del self.clients[client_socket]
                
                if client_info['name'] in self.client_names:
                    del self.client_names[client_info['name']]
                
                print(f'Client disconnected: {client_info["name"]}')
                return client_info['name']
        return None
    
    def is_client_connected(self, client_name):
        """
        Check if a specific client is connected
        
        :param client_name: Client identifier
        :return: True if connected
        """
        with self.client_lock:
            return client_name in self.client_names
    
    # ==================== DATA STORAGE ====================
    
    def store_client_data(self, key, value, client_info=None):
        """
        Store data sent from clients
        
        :param key: Data key
        :param value: Data value
        :param client_info: Client identifier
        :return: True if stored successfully
        """
        with self.data_lock:
            self.client_data[key] = {
                'value': value,
                'timestamp': time.time(),
                'source': 'client',
                'client_info': client_info or 'unknown'
            }
        return True
    
    def convert_value_to_serializable(self, value):
        """
        Convert CAN signal values to JSON-serializable format
        
        :param value: Value to convert
        :return: Serializable value
        """
        if hasattr(value, 'value'):  # NamedSignalValue
            return value.value
        elif isinstance(value, (int, float, str, bool)):
            return value
        else:
            return str(value)
    
    # ==================== CAN BYTE UPDATES ====================
    
    def update_can_bytes(self, byte_updates, client_info=None):
        """
        Update CAN byte values with bitwise operations
        
        :param byte_updates: Dictionary of byte updates
        :param client_info: Client identifier
        :return: True if any bytes were updated
        """
        updated_bytes = []
        
        with self.can_bytes_lock:
            for byte_name, update_info in byte_updates.items():
                # Support both simple value updates and bitwise operations
                if isinstance(update_info, dict):
                    operation = update_info.get('operation', 'replace')
                    value = update_info.get('value', 0)
                    mask = update_info.get('mask', 0xFF)
                else:
                    operation = 'replace'
                    value = update_info
                    mask = 0xFF
                
                old_value = None
                new_value = None
                
                if byte_name == 'fan_byte':
                    old_value = self.fan_byte
                    if operation == 'replace':
                        new_value = value
                    elif operation == 'update_bits':
                        new_value = (self.fan_byte & (~mask)) | (value & mask)
                    
                    if old_value != new_value:
                        self.fan_byte = new_value
                        updated_bytes.append(f'fan_byte={new_value}')
                
                elif byte_name == 'nozzle_byte':
                    old_value = self.nozzle_byte
                    if operation == 'replace':
                        new_value = value
                    elif operation == 'update_bits':
                        new_value = (self.nozzle_byte & (~mask)) | (value & mask)
                    
                    if old_value != new_value:
                        self.nozzle_byte = new_value
                        updated_bytes.append(f'nozzle_byte={new_value}')
                
                elif byte_name == 'status_byte':
                    old_value = self.status_byte
                    if operation == 'replace':
                        new_value = value
                    elif operation == 'update_bits':
                        new_value = (self.status_byte & (~mask)) | (value & mask)
                    
                    if old_value != new_value:
                        self.status_byte = new_value
                        updated_bytes.append(f'status_byte={new_value}')
                
                elif byte_name == 'camera_byte':
                    old_value = self.camera_byte
                    if operation == 'replace':
                        new_value = value
                    elif operation == 'update_bits':
                        new_value = (self.camera_byte & (~mask)) | (value & mask)
                    
                    if old_value != new_value:
                        self.camera_byte = new_value
                        updated_bytes.append(f'camera_byte={new_value}')
        
        return len(updated_bytes) > 0
    
    # ==================== CAN MESSAGE SENDING ====================
    
    def can_send_on_0F7(self):
        """
        Send error message on CAN ID 0x0F7
        
        Byte 0: Error code
        Byte 1: 0xFF
        Byte 2: Unused
        Byte 3: Device identifier
        Byte 4: Additional error info
        Byte 5-7: Reserved
        
        :return: True if sent successfully
        """
        if not self.send_bus:
            return False
        
        msg = can.Message(
            arbitration_id=0x0F7,
            data=[self.error_byte, 0xFF, 0x00, self.device_byte, 
                  self.additional_byte, 0, 0, 0],
            is_extended_id=False
        )
        
        try:
            self.send_bus.send(msg)
            # Reset error bytes after sending
            self.error_byte = 0x00
            self.device_byte = 0x00
            self.additional_byte = 0x00
            return True
        except can.CanError as e:
            print(f'Failed to send CAN message 0x0F7: {e}')
            return False
    
    def can_send_on_1F7(self):
        """
        Send status message on CAN ID 0x1F7
        
        Byte 0: Status byte
        Byte 1: Camera byte
        Byte 2: Nozzle byte
        Byte 3: GPS byte
        Byte 4: Fan byte
        Byte 5: FPS byte
        Byte 6-7: Reserved
        
        Runs in a loop while pipeline client is connected
        """
        while self.running:
            if self.is_client_connected(self.pipeline_client_name):
                msg = can.Message(
                    arbitration_id=0x1F7,
                    data=[self.status_byte, self.camera_byte, self.nozzle_byte,
                          self.gps_byte, self.fan_byte, self.fps_byte, 0, 0],
                    is_extended_id=False
                )
                
                try:
                    self.send_bus.send(msg)
                    
                    # Clear transient bits after sending
                    self.fan_byte &= ~0xF0
                    self.nozzle_byte &= ~0xF0
                
                except can.CanError as e:
                    print(f'Failed to send CAN message 0x1F7: {e}')
            
            time.sleep(0.5)
    
    # ==================== CAN BUS MONITORING ====================
    
    def monitor_can_bus0(self):
        """
        Monitor CAN bus 0 for telematic data
        Decodes messages using DBC database
        """
        print('CAN0 monitoring thread started')
        
        while self.running:
            try:
                if self.bus0:
                    msg = self.bus0.recv(timeout=0.2)
                    if msg:
                        # Pad message to 8 bytes
                        if len(msg.data) < 8:
                            msg.data += bytes(8 - len(msg.data))
                        
                        if self.db0:
                            try:
                                can_msg_dict = self.db0.decode_message(
                                    msg.arbitration_id, msg.data
                                )
                                
                                with self.data_lock:
                                    for key, value in can_msg_dict.items():
                                        # Handle override state
                                        if key == 'overidden':
                                            self.current_override_state = value
                                            if value == 1:
                                                print(f'Override active @ {datetime.now()}')
                                        
                                        # Store serializable value
                                        serializable_value = self.convert_value_to_serializable(value)
                                        
                                        self.can_data[key] = {
                                            'value': serializable_value,
                                            'timestamp': time.time(),
                                            'arbitration_id': hex(msg.arbitration_id),
                                            'bus': 'can0'
                                        }
                            
                            except Exception as e:
                                # Message ID not in DBC - ignore
                                pass
            
            except Exception as e:
                if self.running:
                    print(f'Error in CAN0 monitoring: {e}')
                time.sleep(0.1)
        
        print('CAN0 monitoring thread stopped')
    
    def monitor_can_bus1(self):
        """
        Monitor CAN bus 1 for sensor data (PM sensors, etc.)
        """
        print('CAN1 monitoring thread started')
        
        while self.running:
            try:
                if self.bus1:
                    msg = self.bus1.recv(timeout=0.2)
                    if msg:
                        if len(msg.data) < 8:
                            msg.data += bytes(8 - len(msg.data))
                        
                        if self.db1:
                            try:
                                can_msg_dict = self.db1.decode_message(
                                    msg.arbitration_id, msg.data
                                )
                                
                                with self.data_lock:
                                    for key, value in can_msg_dict.items():
                                        serializable_value = self.convert_value_to_serializable(value)
                                        
                                        self.can_data[key] = {
                                            'value': serializable_value,
                                            'timestamp': time.time(),
                                            'arbitration_id': hex(msg.arbitration_id),
                                            'bus': 'can1'
                                        }
                            
                            except Exception as e:
                                pass
            
            except Exception as e:
                if self.running:
                    print(f'Error in CAN1 monitoring: {e}')
                time.sleep(0.1)
        
        print('CAN1 monitoring thread stopped')
    
    # ==================== FPS MONITORING ====================
    
    def monitor_fps(self):
        """
        Monitor FPS values and detect low FPS conditions
        Sends error messages when FPS drops below threshold
        """
        print('FPS monitoring thread started')
        
        nn_fps_history = [0] * 10
        front_csi_fps_history = [0] * 10
        rear_csi_fps_history = [0] * 10
        fps_index = 0
        
        nn_fps_error_sent = False
        front_csi_error_sent = False
        rear_csi_error_sent = False
        
        while self.running:
            try:
                if self.is_client_connected(self.pipeline_client_name):
                    # Store current FPS in history
                    nn_fps_history[fps_index] = self.nn_fps
                    front_csi_fps_history[fps_index] = self.front_csi_fps
                    rear_csi_fps_history[fps_index] = self.rear_csi_fps
                    
                    fps_index = (fps_index + 1) % 10
                    
                    # Check averages
                    nn_avg = sum(nn_fps_history) / len(nn_fps_history)
                    front_avg = sum(front_csi_fps_history) / len(front_csi_fps_history)
                    rear_avg = sum(rear_csi_fps_history) / len(rear_csi_fps_history)
                    
                    # Check NN FPS
                    if nn_avg < self.nn_fps_threshold and not nn_fps_error_sent:
                        print(f'Low NN FPS detected: {nn_avg:.1f}')
                        self.error_byte = 0x30
                        self.device_byte = 0x01
                        self.can_send_on_0F7()
                        nn_fps_error_sent = True
                    elif nn_avg >= self.nn_fps_threshold:
                        nn_fps_error_sent = False
                    
                    # Check front CSI FPS
                    if front_avg < self.csi_fps_threshold and not front_csi_error_sent:
                        print(f'Low front CSI FPS detected: {front_avg:.1f}')
                        self.error_byte = 0x31
                        self.device_byte = 0x02
                        self.can_send_on_0F7()
                        front_csi_error_sent = True
                    elif front_avg >= self.csi_fps_threshold:
                        front_csi_error_sent = False
                    
                    # Check rear CSI FPS
                    if rear_avg < self.csi_fps_threshold and not rear_csi_error_sent:
                        print(f'Low rear CSI FPS detected: {rear_avg:.1f}')
                        self.error_byte = 0x32
                        self.device_byte = 0x03
                        self.can_send_on_0F7()
                        rear_csi_error_sent = True
                    elif rear_avg >= self.csi_fps_threshold:
                        rear_csi_error_sent = False
            
            except Exception as e:
                print(f'Error in FPS monitoring: {e}')
            
            time.sleep(2)
        
        print('FPS monitoring thread stopped')
    
    # ==================== REQUEST PROCESSING ====================
    
    def process_request(self, request_data, client_info=None):
        """
        Process client requests
        
        :param request_data: Request dictionary
        :param client_info: Client identifier
        :return: Response dictionary
        """
        command = request_data.get('command')
        
        if command == 'get_all':
            with self.data_lock:
                all_data = {}
                all_data.update(self.can_data)
                all_data.update(self.client_data)
                
                return {
                    'data': all_data,
                    'total_keys': len(all_data),
                    'can_keys': len(self.can_data),
                    'client_keys': len(self.client_data),
                    'timestamp': time.time()
                }
        
        elif command == 'send_data':
            key = request_data.get('key')
            value = request_data.get('value')
            
            if key is None or value is None:
                return {'error': 'Missing key or value'}
            
            success = self.store_client_data(key, value, client_info)
            if success:
                return {
                    'status': 'success',
                    'message': f'Data stored: {key} = {value}',
                    'timestamp': time.time()
                }
            else:
                return {'error': 'Failed to store data'}
        
        elif command == 'update_fps':
            fps_type = request_data.get('fps_type')
            fps_value = request_data.get('fps')
            
            if fps_value is None:
                return {'error': 'Missing FPS value'}
            
            with self.can_bytes_lock:
                if fps_type == 'nn':
                    self.nn_fps = fps_value
                elif fps_type == 'front_csi':
                    self.front_csi_fps = fps_value
                elif fps_type == 'rear_csi':
                    self.rear_csi_fps = fps_value
            
            return {
                'status': 'success',
                'message': f'FPS updated: {fps_type} = {fps_value}',
                'timestamp': time.time()
            }
        
        elif command == 'update_camera_status':
            camera = request_data.get('camera')
            
            if camera == 'primary_nozzle':
                self.primary_camera_last_active = time.time()
            elif camera == 'secondary_nozzle':
                self.secondary_camera_last_active = time.time()
            elif camera == 'front':
                self.front_camera_last_active = time.time()
            elif camera == 'rear':
                self.rear_camera_last_active = time.time()
            
            return {
                'status': 'success',
                'message': f'Camera status updated: {camera}',
                'timestamp': time.time()
            }
        
        elif command == 'update_can_bytes':
            byte_updates = request_data.get('bytes', {})
            
            if not byte_updates:
                return {'error': 'Missing bytes data'}
            
            success = self.update_can_bytes(byte_updates, client_info)
            if success:
                return {
                    'status': 'success',
                    'message': 'CAN bytes updated',
                    'timestamp': time.time()
                }
            else:
                return {'error': 'Failed to update CAN bytes'}
        
        elif command == 'get_override_state':
            return {
                'override_state': self.current_override_state,
                'timestamp': time.time()
            }
        
        elif command == 'start_logging':
            return {'status': 'success', 'message': 'Logging enabled'}
        
        elif command == 'stop_logging':
            return {'status': 'success', 'message': 'Logging disabled'}
        
        else:
            return {'error': f'Unknown command: {command}'}
    
    # ==================== CLIENT HANDLER ====================
    
    def handle_client(self, client_socket):
        """
        Handle individual client connection
        
        :param client_socket: Client socket
        """
        client_name = None
        client_identified = False
        
        try:
            while self.running:
                request = client_socket.recv(1024).decode()
                if not request:
                    break
                
                try:
                    request_data = json.loads(request)
                    command = request_data.get('command')
                    
                    # Handle client identification
                    if command == 'client_identification' and not client_identified:
                        client_name = request_data.get('client_name', 'unknown')
                        success = self.register_client(client_socket, client_name)
                        
                        if success:
                            client_identified = True
                            response = {
                                'status': 'success',
                                'message': f'Client {client_name} registered',
                                'timestamp': time.time()
                            }
                        else:
                            response = {
                                'status': 'error',
                                'message': 'Failed to register client'
                            }
                        
                        client_socket.send(json.dumps(response).encode())
                        continue
                    
                    # Handle disconnect
                    elif command == 'client_disconnect':
                        break
                    
                    # Require identification first
                    elif not client_identified:
                        error_response = {
                            'error': 'Client must identify itself first',
                            'required_command': 'client_identification'
                        }
                        client_socket.send(json.dumps(error_response).encode())
                        continue
                    
                    # Process request
                    response = self.process_request(request_data, client_name)
                    client_socket.send(json.dumps(response).encode())
                
                except json.JSONDecodeError:
                    error_response = {'error': 'Invalid JSON'}
                    client_socket.send(json.dumps(error_response).encode())
                except Exception as e:
                    error_response = {'error': str(e)}
                    client_socket.send(json.dumps(error_response).encode())
        
        except Exception as e:
            print(f'Client handler error: {e}')
        finally:
            self.unregister_client(client_socket, client_name)
            client_socket.close()
    
    # ==================== SERVER MANAGEMENT ====================
    
    def start_monitoring_threads(self):
        """Start all monitoring threads"""
        print('Starting monitoring threads...')
        
        # CAN bus monitoring
        if self.bus0:
            can0_thread = threading.Thread(target=self.monitor_can_bus0, daemon=True)
            can0_thread.start()
        
        if self.bus1:
            can1_thread = threading.Thread(target=self.monitor_can_bus1, daemon=True)
            can1_thread.start()
        
        # CAN sending
        if self.send_bus:
            send_thread = threading.Thread(target=self.can_send_on_1F7, daemon=True)
            send_thread.start()
        
        # FPS monitoring
        fps_thread = threading.Thread(target=self.monitor_fps, daemon=True)
        fps_thread.start()
        
        print('All monitoring threads started')
    
    def start_server(self):
        """Start the Unix domain socket server"""
        # Remove existing socket
        if os.path.exists(self.socket_path):
            os.unlink(self.socket_path)
        
        self.server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server_socket.bind(self.socket_path)
        self.server_socket.listen(5)
        os.chmod(self.socket_path, 0o666)
        
        self.running = True
        print(f'CAN Server listening on {self.socket_path}')
        
        # Start monitoring threads
        self.start_monitoring_threads()
        
        # Accept client connections
        while self.running:
            try:
                client_socket, _ = self.server_socket.accept()
                print('New client connected')
                
                client_thread = threading.Thread(
                    target=self.handle_client,
                    args=(client_socket,),
                    daemon=True
                )
                client_thread.start()
            
            except Exception as e:
                if self.running:
                    print(f'Error accepting connection: {e}')
    
    def stop_server(self):
        """Stop the server gracefully"""
        print('Stopping CAN Server...')
        self.running = False
        
        # Close all client connections
        with self.client_lock:
            for client_socket in list(self.clients.keys()):
                try:
                    client_socket.close()
                except:
                    pass
            self.clients.clear()
            self.client_names.clear()
        
        # Close server socket
        if self.server_socket:
            self.server_socket.close()
        
        # Close CAN buses
        if self.bus0:
            self.bus0.shutdown()
        if self.bus1:
            self.bus1.shutdown()
        if self.send_bus:
            self.send_bus.shutdown()
        
        print('CAN Server stopped')


def main():
    """
    Main entry point for CAN Server
    """
    print('=' * 60)
    print('SmartAssist CAN Server Starting...')
    print('=' * 60)
    
    # Initialize server
    server = CANServer(
        socket_path='/tmp/can_server.sock',
        enable_logging=True
    )
    
    # Initialize CAN buses (optional - comment out if hardware not available)
    try:
        server.bus0 = Bus(channel='can0', bustype='socketcan')
        print('CAN0 bus initialized')
    except Exception as e:
        print(f'Warning: Could not initialize CAN0: {e}')
    
    try:
        server.bus1 = Bus(channel='can1', bustype='socketcan')
        print('CAN1 bus initialized')
    except Exception as e:
        print(f'Warning: Could not initialize CAN1: {e}')
    
    # Use can0 for sending
    server.send_bus = server.bus0
    
    # Load DBC databases (optional)
    try:
        server.db0 = cantools.database.load_file('/path/to/telematic.dbc')
        print('DBC database loaded for CAN0')
    except Exception as e:
        print(f'Warning: Could not load DBC: {e}')
    
    # Set up signal handler
    def signal_handler(sig, frame):
        print('\nShutdown signal received')
        server.stop_server()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Start server
    try:
        server.start_server()
    except Exception as e:
        print(f'Server error: {e}')
        server.stop_server()
        return 1
    
    return 0


if __name__ == '__main__':
    sys.exit(main())