import socket
import json
import threading
import time
import os
import cantools
import can
import canopen
from datetime import datetime, timedelta
from can.interface import Bus
import csv
from pathlib import Path
import numpy as np
from utils import Configuration
import pandas as pd


class CanServer:
    def __init__(self, socket_path='/tmp/can_server.sock', enable_logging=True):
        self.socket_path = socket_path
        self.server_socket = None
        self.running = False
        self.can_data = {}  # Dictionary to store CAN messages by key
        self.error_data = {}  # Dictionary to store error messages
        self.client_data = {}  # Dictionary to store data sent from clients
        self.data_lock = threading.Lock()
        self.enable_logging = enable_logging
        self.config = Configuration()  # Load configuration settings
        
        self.can_bytes_lock = threading.Lock()  # Lock for CAN byte updates
        # Client tracking
        self.clients = {}  # Change from list to dict: {socket: client_info}
        self.client_names = {}  # Track client names: {client_name: socket}
        self.client_lock = threading.Lock()  # Lock for client operations

        # CAN sending attributes (from can_subsystem.py)
        self.status_byte = 0x00
        self.camera_byte = 0x00
        self.nozzle_byte = 0x00
        self.gps_byte = 0x00 
        self.fan_byte = 0x00
        self.fps_byte = 0x00
        
        self.error_byte = 0x00
        self.device_byte = 0x00
        self.additional_byte = 0x00

        self.send_bus = None

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

        self.pipeline_client_name = 'pipeline_w_logging.py'
        self.pipeline_check_count = 0
        self.pipeline_was_connected = False

        self.nn_fps_threshold = 20
        self.csi_fps_threshold = 3
        self.nn_fps = 0
        self.front_csi_fps = 0
        self.rear_csi_fps = 0

        self.last_sensor = None
        self.last_sensor_time = None
        self.sensor_weighted_values = {}
        self.dustometer = 0
        self.sensor_min = 0
        self.sensor_max = 1000
        self.sensor_queue = []
        self.sensor_queue_lock = threading.Lock()
        self.last_pm_values = {}
        self.last_pm_values_lock = threading.Lock()

        self.current_override_state = None
        self.override_state_lock = threading.Lock()

        self.camera_timeout = 5

        self.sd_card_full_flag = None

        # Initialize CAN buses but don't start monitoring yet
        self.init_can_buses()
    
    def register_client(self, client_socket, client_name):
        """Register a new client with identification"""
        with self.client_lock:
            client_info = {
                'socket': client_socket,
                'name': client_name,
                'connected_at': time.time(),
                'last_activity': time.time(),
                'request_count': 0
            }
            
            # Remove old client with same name if exists
            if client_name in self.client_names:
                old_socket = self.client_names[client_name]
                if old_socket in self.clients:
                    print(f"Replacing existing client connection for '{client_name}'")
                    del self.clients[old_socket]
                    try:
                        old_socket.close()
                    except:
                        pass
            
            self.clients[client_socket] = client_info
            self.client_names[client_name] = client_socket
            
        print(f"Client '{client_name}' registered successfully")
        return True
    
    def unregister_client(self, client_socket, client_name=None):
        """Unregister a client"""
        with self.client_lock:
            client_info = self.clients.get(client_socket)
            if client_info:
                actual_name = client_info['name']
                connection_duration = time.time() - client_info['connected_at']
                
                # Remove from both tracking dicts
                del self.clients[client_socket]
                if actual_name in self.client_names:
                    del self.client_names[actual_name]
                
                print(f"Client '{actual_name}' disconnected after {connection_duration:.2f} seconds ({client_info['request_count']} requests)")
                return actual_name
            
        return client_name or "unknown"

    def is_client_connected(self, client_name):
        """Check if a specific client is currently connected"""
        with self.client_lock:
            return client_name in self.client_names

    def monitor_pipeline_client(self):
        """Simple pipeline client monitoring - check every 5 seconds"""
        print(f"Started monitoring '{self.pipeline_client_name}' client")
        
        while self.running:
            try:
                is_connected = self.is_client_connected(self.pipeline_client_name)
                
                if is_connected:
                    if self.pipeline_check_count > 0:
                        print(f"Pipeline client '{self.pipeline_client_name}' is now connected")
                    self.pipeline_check_count = 0  
                    self.pipeline_was_connected = True  
                    self.nozzle_byte |= 0x10
                else:
                    self.pipeline_check_count += 1

                    if self.pipeline_check_count == 1 and self.pipeline_was_connected:
                        print(f"Pipeline client '{self.pipeline_client_name}' has disconnected")
                        self.error_byte = 0x02
                        self.device_byte = 0x00  
                        self.additional_byte = 0x00
                        self.can_send_on_0F7()
                        self.nozzle_byte |= 0x00
                    
                    if self.pipeline_check_count == 10 and not self.pipeline_was_connected:
                        self.error_byte = 0x01  
                        self.device_byte = 0x00  #
                        self.additional_byte = 0x00
                        self.can_send_on_0F7()
                        self.nozzle_byte |= 0x00
                
                time.sleep(6)
                
            except Exception as e:
                print(f"Error in pipeline monitoring: {e}")
                time.sleep(6)
        
        print("Pipeline monitoring thread stopped")
    
    def check_sd_card_status(self):
        """Check SD card status and update GPS byte accordingly"""
        sd_card_path = '/mnt/syslogic_sd_card'
        while self.running:
            try:
                if os.path.ismount(sd_card_path):
                    # Get disk usage statistics
                    stat = os.statvfs(sd_card_path)
                    
                    # Calculate used percentage
                    total_space = stat.f_blocks * stat.f_frsize
                    free_space = stat.f_bavail * stat.f_frsize
                    used_space = total_space - free_space
                    used_percentage = (used_space / total_space) * 100
                    
                    print(f"SD card is mounted - Used: {used_percentage:.1f}%")
                    
                    if used_percentage >= 90:
                        print(f"Warning: SD card is {used_percentage:.1f}% full (threshold: 90%)")
                        self.sd_card_full_flag = 1
                else:
                    print("SD card is not mounted")
            except Exception as e:
                print(f"Error checking SD card status: {e}")
                
            time.sleep(60)
                 

    def init_can_buses(self):
        """Initialize CAN buses"""
        try:
            # CAN bus filters for telematic data
            telematic_filters = [
                {"can_id": 0x203, "can_mask": 0xFFF, "extended": False}, # TrackerMsg1
                {"can_id": 0x202, "can_mask": 0xFFF, "extended": False}, # VehicleSerialNumber
                {"can_id": 0x303, "can_mask": 0xFFF, "extended": False}, # TrackerMsg2
                {"can_id": 0x714, "can_mask": 0xFFF, "extended": False}, # JVMheartbeat
                {"can_id": 0x505, "can_mask": 0xFFF, "extended": False}, # TrackerMsg8
                {"can_id": 0x504, "can_mask": 0xFFF, "extended": False}, # TrackerErrorMsg4
                {"can_id": 0x403, "can_mask": 0xFFF, "extended": False}, # TrackerMsg3
                {"can_id": 0x284, "can_mask": 0xFFF, "extended": False}, # Altitude_time
                {"can_id": 0x285, "can_mask": 0xFFF, "extended": False}, # Heading_Satelites
                {"can_id": 0x384, "can_mask": 0xFFF, "extended": False}, # Longitude_Latitude
                {"can_id": 0x277, "can_mask": 0xFFF, "extended": False}, # JCMtoSmartSweeperECU
            ]
            

            print("Initializing CAN buses...")
            
            try:
                self.bus1 = Bus(interface='socketcan', channel='can0', bitrate=250000, can_filters=telematic_filters)
                print("CAN0 (telematic) bus initialized")
            except Exception as e:
                print(f"Failed to initialize CAN0: {e}")
                self.bus1 = None
                
            try:
                self.bus2 = Bus(interface='socketcan', channel='can1', bitrate=250000)
                print("CAN1 (particle and pressure) bus initialized")
            except Exception as e:
                print(f"Failed to initialize CAN1: {e}")
                self.bus2 = None
            
            try:
                self.send_bus = Bus(interface='socketcan', channel='can0', bitrate=250000)
                print("CAN send bus initialized")
            except Exception as e:
                print(f"Failed to initialize CAN send bus: {e}")
                self.send_bus = None
            
            try:
                self.db1 = cantools.database.load_file('/mnt/ssd/csi_pipeline/dbc/TMS_V1_44_WIP.dbc')
                self.db2 = cantools.database.load_file('/mnt/ssd/csi_pipeline/dbc/PM_Sensor._V2dbc.dbc')
                print("DBC files loaded successfully")
            except Exception as e:
                print(f"Failed to load DBC files: {e}")
                self.db1 = None
                self.db2 = None

        except Exception as e:
            print(f"Error initializing CAN buses: {e}")
            self.bus1 = None
            self.bus2 = None
            self.db1 = None
            self.db2 = None

    def convert_value_to_serializable(self, value):
        """Convert cantools values to JSON serializable format"""
        if hasattr(value, 'value'):  # NamedSignalValue
            return value.value
        elif isinstance(value, (int, float, str, bool)):
            return value
        else:
            return str(value)  # Convert anything else to string
            
    def store_client_data(self, key, value, client_info=None):
        """Store data sent from clients"""
        with self.data_lock:
            self.client_data[key] = {
                'value': value,
                'timestamp': time.time(),
                'source': 'client',
                'client_info': client_info or 'unknown'
            }
        #print(f"SERVER: Received client data - {key} = {value} from {client_info or 'unknown client'}")
        return True

    def update_can_bytes(self, byte_updates, client_info=None):
        """Update CAN byte values from client data with optional bitwise operations"""
        updated_bytes = []
        #significant_bit_changed = False
        
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
                
                if byte_name == 'fan_byte':
                    old_value = self.fan_byte
                    
                    if operation == 'replace':
                        new_value = value
                    elif operation == 'update_bits':
                        # Clear specified bits and set new value
                        new_value = (self.fan_byte & (~mask)) | (value & mask)
                    else:
                        continue  # Skip unknown operations
                        
                    if old_value != new_value:
                        self.fan_byte = new_value
                        updated_bytes.append(f"fan_byte={new_value} (was {old_value})")
                        #significant_bit_changed = True
                        
                elif byte_name == 'nozzle_byte':
                    old_value = self.nozzle_byte
                    
                    if operation == 'replace':
                        new_value = value
                    elif operation == 'update_bits':
                        new_value = (self.nozzle_byte & (~mask)) | (value & mask)
                    else:
                        continue
                        
                    if old_value != new_value:
                        self.nozzle_byte = new_value
                        updated_bytes.append(f"nozzle_byte={new_value} (was {old_value})")
                        #significant_bit_changed = True

                elif byte_name == 'status_byte':
                    old_value = self.status_byte
                    
                    if operation == 'replace':
                        new_value = value
                    elif operation == 'update_bits':
                        new_value = (self.status_byte & (~mask)) | (value & mask)
                    else:
                        continue
                        
                    if old_value != new_value:
                        self.status_byte = new_value
                        updated_bytes.append(f"status_byte={new_value} (was {old_value})")

                # Add other bytes as needed...
                elif byte_name == 'camera_byte':
                    old_value = self.camera_byte
                    
                    if operation == 'replace':
                        new_value = value
                    elif operation == 'update_bits':
                        new_value = (self.camera_byte & (~mask)) | (value & mask)
                    else:
                        continue
                        
                    if old_value != new_value:
                        self.camera_byte = new_value
                        updated_bytes.append(f"camera_byte={new_value} (was {old_value})")

        #if updated_bytes:
            #print(f"SERVER: Updated CAN bytes {', '.join(updated_bytes)} from {client_info or 'unknown client'}")

            #if significant_bit_changed:
            #    print("SERVER: Bytes changed - sending immediate 0x1F7 message")
            #    self.can_send_on_1F7()
        
        return len(updated_bytes) > 0
    
    def monitor_fps(self):
        nn_fps_history = [0] * 10  
        front_csi_fps_history = [0] * 10  
        rear_csi_fps_history = [0] * 10  
        fps_index = 0  
        array_filled = False  
        array_refreshed = False  
        
        # Track error states for each FPS type
        nn_fps_error_sent = False
        front_csi_error_sent = False
        rear_csi_error_sent = False

        while self.running:
            try:
                if self.is_client_connected(self.pipeline_client_name):
                    # Get current FPS values
                    current_nn_fps = self.nn_fps
                    current_front_csi_fps = self.front_csi_fps
                    current_rear_csi_fps = self.rear_csi_fps
                    
                    if current_nn_fps > 0 or current_front_csi_fps > 0 or current_rear_csi_fps > 0:
                        nn_fps_history[fps_index] = current_nn_fps
                        front_csi_fps_history[fps_index] = current_front_csi_fps
                        rear_csi_fps_history[fps_index] = current_rear_csi_fps
                        
                        fps_index = (fps_index + 1) % 10
                        
                        if fps_index == 0 and not array_filled:
                            array_filled = True
                            print("FPS monitoring: Initial array filled, refreshing arrays to avoid startup false alarms...")
                            # Reset arrays and index for a fresh start
                            nn_fps_history = [0] * 10
                            front_csi_fps_history = [0] * 10
                            rear_csi_fps_history = [0] * 10
                            fps_index = 0
                            array_refreshed = True
                            continue  # Skip this iteration and start fresh
                        elif fps_index == 0 and array_filled and not array_refreshed:
                            array_refreshed = True
                            print("FPS monitoring: Post-refresh array filled, monitoring now active")
                        
                        # Only start monitoring after both array_filled and array_refreshed are True
                        if array_filled and array_refreshed:
                            # NN FPS monitoring
                            non_zero_nn_values = [fps for fps in nn_fps_history if fps > 0]
                            if non_zero_nn_values:
                                avg_nn_fps = sum(non_zero_nn_values) / len(non_zero_nn_values)
                                avg_fps_byte = int(avg_nn_fps)
                                self.fps_byte = int(hex(avg_fps_byte), 16)
                                
                                if avg_nn_fps < self.nn_fps_threshold:
                                    # Only send error if we haven't already sent one for this condition
                                    if not nn_fps_error_sent:
                                        print(f"NN FPS below threshold: {avg_nn_fps:.1f} < {self.nn_fps_threshold}")
                                        self.error_byte = 0x03
                                        self.device_byte = 0x00
                                        self.additional_byte = 0x01
                                        self.can_send_on_0F7()
                                        nn_fps_error_sent = True
                                else:
                                    # FPS is above threshold - reset error flag so we can send again if it drops
                                    if nn_fps_error_sent:
                                        print(f"NN FPS recovered: {avg_nn_fps:.1f} >= {self.nn_fps_threshold}")
                                    nn_fps_error_sent = False
                            
                            # Front CSI FPS monitoring
                            non_zero_front_csi_values = [fps for fps in front_csi_fps_history if fps > 0]
                            if non_zero_front_csi_values:
                                avg_front_csi_fps = sum(non_zero_front_csi_values) / len(non_zero_front_csi_values)
                                
                                if avg_front_csi_fps < self.csi_fps_threshold:
                                    if not front_csi_error_sent:
                                        print(f"Front CSI FPS below threshold: {avg_front_csi_fps:.1f} < {self.csi_fps_threshold}")
                                        self.error_byte = 0x04
                                        self.device_byte = 0x12
                                        self.additional_byte = 0x01
                                        self.can_send_on_0F7()
                                        front_csi_error_sent = True
                                else:
                                    if front_csi_error_sent:
                                        print(f"Front CSI FPS recovered: {avg_front_csi_fps:.1f} >= {self.csi_fps_threshold}")
                                    front_csi_error_sent = False
                            
                            # Rear CSI FPS monitoring
                            non_zero_rear_csi_values = [fps for fps in rear_csi_fps_history if fps > 0]
                            if non_zero_rear_csi_values:
                                avg_rear_csi_fps = sum(non_zero_rear_csi_values) / len(non_zero_rear_csi_values)
                                
                                if avg_rear_csi_fps < self.csi_fps_threshold:
                                    if not rear_csi_error_sent:
                                        print(f"Rear CSI FPS below threshold: {avg_rear_csi_fps:.1f} < {self.csi_fps_threshold}")
                                        self.error_byte = 0x04
                                        self.device_byte = 0x13
                                        self.additional_byte = 0x01
                                        self.can_send_on_0F7()
                                        rear_csi_error_sent = True
                                else:
                                    if rear_csi_error_sent:
                                        print(f"Rear CSI FPS recovered: {avg_rear_csi_fps:.1f} >= {self.csi_fps_threshold}")
                                    rear_csi_error_sent = False
                else:
                    if array_filled or array_refreshed:
                        print("Pipeline client disconnected, resetting FPS monitoring state")
                        array_filled = False
                        array_refreshed = False
                        fps_index = 0
                        nn_fps_history = [0] * 10
                        front_csi_fps_history = [0] * 10
                        rear_csi_fps_history = [0] * 10
                        nn_fps_error_sent = False
                        front_csi_error_sent = False
                        rear_csi_error_sent = False

            except Exception as e:
                print(f"Error in FPS monitoring: {e}")
            time.sleep(1)

    def can_sdo_server_construct(self):
        node_id = 0x77
        obj_dict = canopen.ObjectDictionary()

        device_name = canopen.objectdictionary.Variable('Device Name', 0x1008, 0)
        device_name.data_type = canopen.objectdictionary.VISIBLE_STRING
        device_name.access_type = "ro"
        device_name.default = 'AI NODE'
        obj_dict.add_object(device_name)

        hw_version = canopen.objectdictionary.Variable('Hardware Version', 0x1009, 0)
        hw_version.data_type = canopen.objectdictionary.VISIBLE_STRING
        hw_version.access_type = "ro"
        hw_version.default = 'beta'
        obj_dict.add_object(hw_version)

        app_version = canopen.objectdictionary.Variable('Application Version', 0x100A, 0)
        app_version.data_type = canopen.objectdictionary.VISIBLE_STRING
        app_version.access_type = "ro"
        app_version.default = 'beta'
        obj_dict.add_object(app_version)

        software_versioning_array = canopen.objectdictionary.Array('Software Versioning', 0x4559)
        sbom_version = canopen.objectdictionary.Variable('SBOM Version', 0x4559, 1)
        sbom_version.data_type = canopen.objectdictionary.VISIBLE_STRING
        sbom_version.access_type = "ro"
        sbom_version.default = 'beta'
        smart_pickup_model_version = canopen.objectdictionary.Variable('Smart Pickup Model Version', 0x4559, 2)
        smart_pickup_model_version.data_type = canopen.objectdictionary.VISIBLE_STRING
        smart_pickup_model_version.access_type = "ro"
        smart_pickup_model_version.default = '2.5.3'
        smart_csi_model_version = canopen.objectdictionary.Variable('Smart CSI Model Version', 0x4559, 3)
        smart_csi_model_version.data_type = canopen.objectdictionary.VISIBLE_STRING
        smart_csi_model_version.access_type = "ro"
        smart_csi_model_version.default = '2.0.0'
        software_versioning_array.add_member(sbom_version)
        software_versioning_array.add_member(smart_pickup_model_version)
        software_versioning_array.add_member(smart_csi_model_version)
        obj_dict.add_object(software_versioning_array)

        network = canopen.Network()
        local_node = canopen.LocalNode(node_id, obj_dict)
        network.add_node(local_node)
        network.connect(channel='can0', bustype='socketcan')
        return
                
    def start_monitoring_threads(self):
        """Start CAN monitoring threads"""
        if self.bus1:
            self.can_thread1 = threading.Thread(target=self.monitor_can_bus1)
            self.can_thread1.daemon = True
            self.can_thread1.start()
            print("Started CAN0 monitoring thread")
            
        if self.bus2:
            self.can_thread2 = threading.Thread(target=self.monitor_can_bus2)
            self.can_thread2.daemon = True
            self.can_thread2.start()
            print("Started CAN1 monitoring thread")

        self.sd_card_monitor_thread = threading.Thread(target=self.check_sd_card_status)
        self.sd_card_monitor_thread.daemon = True
        self.sd_card_monitor_thread.start()
        print("Started SD card monitoring thread")

        self.can_sdo_thread = threading.Thread(target=self.can_sdo_server_construct)
        self.can_sdo_thread.daemon = True
        self.can_sdo_thread.start()
        print("Started CAN SDO server thread")
        
        self.pipeline_monitor_thread = threading.Thread(target=self.monitor_pipeline_client)
        self.pipeline_monitor_thread.daemon = True
        self.pipeline_monitor_thread.start()
        print("Started pipeline monitoring thread")

        self.fps_monitor_thread = threading.Thread(target=self.monitor_fps)
        self.fps_monitor_thread.daemon = True
        self.fps_monitor_thread.start()
        print("Started FPS monitoring thread")

        self.sensor_monitor_thread = threading.Thread(target=self.monitor_sensors)
        self.sensor_monitor_thread.daemon = True
        self.sensor_monitor_thread.start()
        print("Started particle sensor monitoring thread")
        
        self.camera_monitoring_thread = threading.Thread(target=self.camera_monitoring)
        self.camera_monitoring_thread.daemon = True
        self.camera_monitoring_thread.start()

        self.can_thread_1F7 = threading.Thread(target=self.can_send_on_1F7)
        self.can_thread_1F7.daemon = True
        self.can_thread_1F7.start()
        print("Started 1F7 CAN message sending thread")

    def camera_monitoring(self):
        """Monitor camera status"""
       
        while self.running:
            if self.is_client_connected(self.pipeline_client_name):
                if self.primary_camera_last_active and not self.primary_camera_failed and not self.primary_camera_inactive:
                    self.primary_camera_inactive_count = 0
                    if time.time() - self.primary_camera_last_active > self.camera_timeout:
                        self.error_byte = 0x11
                        self.device_byte = 0x10
                        self.can_send_on_0F7()
                        self.primary_camera_failed = True
                        self.camera_byte &= ~0x40
                elif not self.primary_camera_last_active and not self.primary_camera_inactive and not self.primary_camera_failed:
                    self.primary_camera_inactive_count += 1
                    if self.primary_camera_inactive_count >= 3:
                        print("Primary camera inactive detected")
                        self.error_byte = 0x10
                        self.device_byte = 0x10
                        self.can_send_on_0F7()
                        self.primary_camera_inactive = True
                        self.camera_byte &= ~0x04

                if self.secondary_camera_last_active and not self.secondary_camera_failed and not self.secondary_camera_inactive:
                    self.secondary_camera_inactive_count = 0
                    if time.time() - self.secondary_camera_last_active > self.camera_timeout:
                        self.error_byte = 0x11
                        self.device_byte = 0x11
                        self.can_send_on_0F7()
                        self.secondary_camera_failed = True
                        self.camera_byte &= ~0x80
                elif not self.secondary_camera_last_active and not self.secondary_camera_inactive and not self.secondary_camera_failed:
                    self.secondary_camera_inactive_count += 1
                    if self.secondary_camera_inactive_count >= 3:
                        print("Secondary camera inactive detected")
                        self.error_byte = 0x10
                        self.device_byte = 0x11
                        self.can_send_on_0F7()
                        self.secondary_camera_inactive = True
                        self.camera_byte &= ~0x08

                if self.front_camera_last_active and not self.front_camera_failed and not self.front_camera_inactive:
                    self.front_camera_inactive_count = 0
                    if time.time() - self.front_camera_last_active > self.camera_timeout:
                        self.error_byte = 0x11
                        self.device_byte = 0x12
                        self.can_send_on_0F7()
                        self.front_camera_failed = True
                        self.camera_byte &= ~0x10
                elif not self.front_camera_last_active and not self.front_camera_inactive and not self.front_camera_failed:
                    self.front_camera_inactive_count += 1
                    if self.front_camera_inactive_count >= 3:
                        print("Front camera inactive detected")
                        self.error_byte = 0x10
                        self.device_byte = 0x12
                        self.can_send_on_0F7()
                        self.front_camera_inactive = True
                        self.camera_byte &= ~0x01

                if self.rear_camera_last_active and not self.rear_camera_failed and not self.rear_camera_inactive:
                    self.rear_camera_inactive_count = 0
                    if time.time() - self.rear_camera_last_active > self.camera_timeout:
                        self.error_byte = 0x11
                        self.device_byte = 0x13
                        self.can_send_on_0F7()
                        self.rear_camera_failed = True
                        self.camera_byte &= ~0x20
                elif not self.rear_camera_last_active and not self.rear_camera_inactive and not self.rear_camera_failed:
                    self.rear_camera_inactive_count += 1
                    if self.rear_camera_inactive_count >= 3:
                        print("Rear camera inactive detected")
                        self.error_byte = 0x10
                        self.device_byte = 0x13
                        self.can_send_on_0F7()
                        self.rear_camera_inactive = True
                        self.camera_byte &= ~0x02
            
            time.sleep(5)

    def monitor_can_bus1(self):
        """Monitor CAN bus 1 for telematic data"""
        print("CAN0 monitoring thread started")
        
        while self.running:
            try:
                if self.bus1:
                    msg = self.bus1.recv(timeout=0.2)  # 200 ms timeout
                    if msg:
                        if len(msg.data) < 8:
                            msg.data += bytes(8 - len(msg.data))
                        if self.db1:
                            try:
                                can_msg_dict = self.db1.decode_message(msg.arbitration_id, msg.data)
                                
                                with self.data_lock:
                                    for key, value in can_msg_dict.items():
                                        if key == "overidden":
                                             self.current_override_state = value
                                             if value == 1:
                                                print(f'Overidden {value} @ {datetime.now()} in can bus')

                                        # Convert to serializable format
                                        serializable_value = self.convert_value_to_serializable(value)
                                        
                                        self.can_data[key] = {
                                            'value': serializable_value,
                                            'timestamp': time.time(),
                                            'arbitration_id': hex(msg.arbitration_id),
                                            'bus': 'can0'
                                        }
                            except Exception as e:
                                #print(f"Failed to decode message ID 0x{msg.arbitration_id:X}: {e}")
                                pass
                        else:
                            print("No DBC database available for decoding")
            except Exception as e:
                # Timeout is expected, don't print error for that
                if "timed out" not in str(e).lower() and self.running:
                    print(f"Error in CAN0 monitoring: {e}")

        print("CAN0 monitoring thread stopped")

    def monitor_can_bus2(self):
        """Monitor CAN bus 2 for particle and pressure data"""
        print("CAN1 monitoring thread started")
        SENSOR_IDS = {448, 449, 450, 451, 452, 453}
        
        while self.running:
            try:
                if self.bus2:
                    msg = self.bus2.recv(timeout=0.2)  # 200 ms timeout
                    if msg:
                        if msg.arbitration_id in SENSOR_IDS:
                            converted_data = bytearray(msg.data)
                            if len(msg.data) >= 8:
                                converted_data[2], converted_data[3] = converted_data[3], converted_data[2]
                                converted_data[4], converted_data[5] = converted_data[5], converted_data[4]
                                converted_data[6], converted_data[7] = converted_data[7], converted_data[6]
                        else:
                            converted_data = msg.data
                        if self.db2:
                            try:
                                can_msg_dict = self.db2.decode_message(msg.arbitration_id,bytes(converted_data))
                                can_msg_dict['dustometer'] = self.dustometer
                                if msg.arbitration_id in SENSOR_IDS:
                                    # Map sensor IDs: 449->1, 450->2, 451->3, 452->4, 453->5
                                    id_mapping = {448: 0, 449: 1, 450: 2, 451: 3, 452: 4, 453: 5}
                                    sensor_id = id_mapping.get(msg.arbitration_id, msg.arbitration_id)
                                    can_msg_dict['sensor_id'] = sensor_id
                                
                                if 'SG_PM10_ug_per_m3_10s' in can_msg_dict:
                                    pm10_value = can_msg_dict['SG_PM10_ug_per_m3_10s']
                                    weight = self.get_sensor_weight(sensor_id)
                                    weighted_score = pm10_value * weight
                                    self.sensor_weighted_values[sensor_id] = weighted_score
                                    can_msg_dict['sensor_weighted_score'] = weighted_score
                                    
                                    # Store the last known PM value for this sensor
                                    with self.last_pm_values_lock:
                                        self.last_pm_values[sensor_id] = {
                                            'value': pm10_value,
                                            'timestamp': time.time(),
                                            'arbitration_id': hex(msg.arbitration_id),
                                            'bus': 'can1'
                                        }
                                    
                                    self.dustometer = self.calculate_normalized_dustometer()
                                    can_msg_dict['dustometer'] = self.dustometer

                                # Add to particle sensor queue if it's particle sensor data
                                if msg.arbitration_id in SENSOR_IDS:
                                    sensor_data_entry = {}
                                    for key, value in can_msg_dict.items():
                                        serializable_value = self.convert_value_to_serializable(value)
                                        sensor_data_entry[key] = {
                                            'value': serializable_value,
                                            'timestamp': time.time(),
                                            'arbitration_id': hex(msg.arbitration_id),
                                            'bus': 'can1'
                                        }
                                    
                                    # Add to queue for PM logging
                                    with self.sensor_queue_lock:
                                        self.sensor_queue.append(sensor_data_entry)
                                        # Keep queue size manageable (last 100 entries)
                                        if len(self.sensor_queue) > 100:
                                            self.sensor_queue.pop(0)

                                with self.data_lock:
                                    for key, value in can_msg_dict.items():
                                        # Convert to serializable format
                                        serializable_value = self.convert_value_to_serializable(value)
                                        
                                        # Convert pressure if needed
                                        if key == "Pressure1":
                                            serializable_value = ((serializable_value / 5000.0) * 0.4 - 0.2) * 100000

                                        self.can_data[key] = {
                                            'value': serializable_value,
                                            'timestamp': time.time(),
                                            'arbitration_id': hex(msg.arbitration_id),
                                            'bus': 'can1'
                                        }
                                    
                            except Exception as e:
                                #print(f"Failed to decode message ID 0x{msg.arbitration_id:X}: {e}")
                                pass
                        else:
                            print("No DBC database available for decoding")
            except Exception as e:
                # Timeout is expected, don't print error for that
                if "timed out" not in str(e).lower() and self.running:
                    print(f"Error in CAN1 monitoring: {e}")
                    
        print("CAN1 monitoring thread stopped")

    def calculate_normalized_dustometer(self):
        """
        Calculate normalized dustometer value from weighted sensor values
        Returns a value between 0-100
        """
        if not self.sensor_weighted_values:
            return 0
        
        # Sum all weighted scores
        total_weighted_score = sum(self.sensor_weighted_values.values())
        
        # Calculate the theoretical max possible value
        # Max value (1000) * sum of all weights
        all_weights = [self.get_sensor_weight(i) for i in range(1, 6)]
        max_possible_weighted_sum = self.sensor_max * sum(all_weights)
        
        # Calculate the theoretical min possible value  
        min_possible_weighted_sum = self.sensor_min * sum(all_weights)
        
        # Normalize between 0-100
        if max_possible_weighted_sum == min_possible_weighted_sum:
            return 0  # Avoid division by zero
        
        normalized_value = ((total_weighted_score - min_possible_weighted_sum) / 
                        (max_possible_weighted_sum - min_possible_weighted_sum)) * 100
        
        # Clamp between 0-100
        normalized_value = max(0, min(100, normalized_value))
        
        return int(normalized_value)

    def get_sensor_weight(self, sensor_id):
        """Return weight based on sensor position/importance"""
        sensor_weights = {
            1: 0.15,  # PM_SENSOR_01 Front
            2: 0.15, # PM_SENSOR_02 Sweep Gear 
            3: 0.2,  # PM_SENSOR_03 Rear Axel 
            4: 0.2,  # PM_SENSOR_04 Rear Top 
            5: 0.3   # PM_SENSOR_05 Fan Outlet
        }
        return sensor_weights.get(sensor_id, 0.1)

    def monitor_sensors(self):
        sensors = {
            'sensor1': {'heartbeat_id': '0x740', 'readings_id': '0x1c0', 'status': False, 'device_id': 0x20, 'last_active': None},
            'sensor2': {'heartbeat_id': '0x741', 'readings_id': '0x1c1', 'status': False, 'device_id': 0x21, 'last_active': None},
            'sensor3': {'heartbeat_id': '0x742', 'readings_id': '0x1c2', 'status': False, 'device_id': 0x22, 'last_active': None},
            'sensor4': {'heartbeat_id': '0x743', 'readings_id': '0x1c3', 'status': False, 'device_id': 0x23, 'last_active': None},
            'sensor5': {'heartbeat_id': '0x744', 'readings_id': '0x1c4', 'status': False, 'device_id': 0x24, 'last_active': None}
        }
        while self.running:
            try:
                for sensor_name, sensor_info in sensors.items():
                    sensor_id = sensor_info['heartbeat_id']
                    readings_id = sensor_info['readings_id']
                    
                    with self.data_lock:
                        for key, value in self.can_data.items():
                            if value.get('arbitration_id') == sensor_id:
                                sensors[sensor_name]['status'] = True
                                sensors[sensor_name]['last_active'] = time.time()
                                break
                    
                    if sensors[sensor_name]['status'] == False:
                        self.error_byte = 0x20
                        self.device_byte = sensor_info['device_id']
                        self.additional_byte = 0x00
                        self.can_send_on_0F7()
                        sensors[sensor_name]['status'] = None
                    elif sensor_info['last_active'] is not None:
                        if time.time() - sensor_info['last_active'] > 10:
                            self.error_byte = 0x21
                            self.device_byte = sensor_info['device_id']
                            self.additional_byte = 0x00
                            self.can_send_on_0F7()
                            sensors[sensor_name]['status'] = None
                        else:
                            for key, value in self.can_data.items():
                                if value.get('arbitration_id') == readings_id:
                                    if key == 'SG_Sleep_Mode' and value['value'] == 1:
                                        self.error_byte = 0x28
                                        self.device_byte = sensor_info['device_id']
                                        self.additional_byte = 0x00
                                        self.can_send_on_0F7()
                                    if key == 'SG_Degraded_mode' and value['value'] == 1:
                                        self.error_byte = 0x27
                                        self.device_byte = sensor_info['device_id']
                                        self.additional_byte = 0x00
                                        self.can_send_on_0F7()
                                    if key == 'SG_Heater_Error' and value['value'] == 1:
                                        self.error_byte = 0x26
                                        self.device_byte = sensor_info['device_id']
                                        self.additional_byte = 0x00
                                        self.can_send_on_0F7()
                                    if key == 'SG_Temp_Humidity_Error' and value['value'] == 1:
                                        self.error_byte = 0x25
                                        self.device_byte = sensor_info['device_id']
                                        self.additional_byte = 0x00
                                        self.can_send_on_0F7()
                                    if key == 'SG_Fan_Error' and value['value'] == 1:
                                        self.error_byte = 0x24
                                        self.device_byte = sensor_info['device_id']
                                        self.additional_byte = 0x00
                                        self.can_send_on_0F7()
                                    if key == 'SG_Memory_Error' and value['value'] == 1:
                                        self.error_byte = 0x23
                                        self.device_byte = sensor_info['device_id']
                                        self.additional_byte = 0x00
                                        self.can_send_on_0F7()
                                    if key == 'SG_Laser_Error' and value['value'] == 1:
                                        self.error_byte = 0x22
                                        self.device_byte = sensor_info['device_id']
                                        self.additional_byte = 0x00
                                        self.can_send_on_0F7()

            except Exception as e:
                print(f"Error checking for sensor data: {e}")
            time.sleep(5)

    def can_send_on_0F7(self):
        '''
        Byte 0 : General error overview 
        Byte 1 : FF
        Byte 2 : Unused
        Byte 3 : Device identifier
        Byte 4 : Additional error information
        Byte 5 : 
            Bit 1: Generic_Error
            Bit 2: Current_Error
            Bit 3: Voltage_Error
            Bit 4: Temperature_Error
            Bit 5: Comms_Error_Overrun
            Bit 6: Device_Profile_Specific_Error
            Bit 7: Reserved
        Byte 6 :
            Bit 0: Manufacturer_Specific_Error
            Bit 1: AI_Reported_Code
        Byte 7: Reserved_2
        '''
        msg = can.Message(arbitration_id=0x0F7, data=[self.error_byte, 0xFF, 0x00, self.device_byte, self.additional_byte, 0, 0, 0], is_extended_id=False)
        try:
            self.send_bus.send(msg)
            self.error_byte = 0x00 
            self.device_byte = 0x00
            self.additional_byte = 0x00
        except can.CanError:
            print("Failed to send CAN message 0x0F7")
            return 

    def can_send_on_1F7(self):
        '''
        Byte 0 : Status
        Byte 1 :
            Bit 0: front_camera_init_state
            Bit 1: rear_camera_init_state
            Bit 2: nozzle_1_camera_init_state
            Bit 3: nozzle_2_camera_init_state
            Bit 4: front_camera_runtime_state
            Bit 5: rear_camera_runtime_state
            Bit 6: nozzle_1_camera_runtime_state
            Bit 7: nozzle_2_camera_runtime_state
        Byte 2 :
            Bit 0-1: nozzle_1_state
            Bit 2-3: nozzle_2_state
            Bit 4-7: AI_APP_STATUS
        Byte 3 : 
            Bit 0-2: AVG_GPS_SPEED
            Bit 3: GPS_SPEED_STATUS_ERROR
            Bit 4-5: WSB_State
        Byte 4 :
            Bit 0-3: FAN_REQUEST
            Bit 4: Nozzle_clear
            Bit 5: Nozzle_blocked
            Bit 6: Nozzle_Action_Object
            Bit 7: Nozzle_Gravel
        Byte 5 :
            Bit 0: DIWC_0
            Bit 1: DIWC_1
            Bit 2: DIWC_2
            Bit 3: DIWC_3
            Bit 4: DIWC_4
            Bit 5: DIWC_5
            Bit 6: DIWC_6
            Bit 7: DIWC_7
        Byte 6:
            Bit 0-7: CSI
        Byte 7:
            Bit 0: Dustometer
            Bit 1: BlockTooLong
            Bit 2: OverSpeed
        '''
        while self.running:
            if self.is_client_connected(self.pipeline_client_name):
                msg = can.Message(arbitration_id=0x1F7, data=[self.status_byte, self.camera_byte, self.nozzle_byte, self.gps_byte, self.fan_byte, self.fps_byte, 0, 0], is_extended_id=False)
                try:   
                    self.send_bus.send(msg)
                    self.fan_byte &= ~0x10
                    self.fan_byte &= ~0x20
                    self.fan_byte &= ~0x40
                    self.fan_byte &= ~0x80
                    self.nozzle_byte &= ~0x10
                    self.nozzle_byte &= ~0x20
                    self.nozzle_byte &= ~0x40
                    self.nozzle_byte &= ~0x80
                except can.CanError:
                    return 
                time.sleep(0.5)

    def can_send_on_2F7(self):
        '''
        Byte 0 : SmartPickup
        Byte 1 : SmartCSI
        '''
        msg = can.Message(arbitration_id=0x2F7, data=[0, 0, 0, 0, 0, 0, 0, 0], is_extended_id=False)
        try:
            self.send_bus.send(msg)
        except can.CanError:
            print("Failed to send CAN message 0x2F7")
            return 

    def handle_client(self, client_socket):
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
                    
                    if command == 'client_identification' and not client_identified:
                        client_name = request_data.get('client_name', 'unknown_client')
                        success = self.register_client(client_socket, client_name)
                        
                        if success:
                            client_identified = True
                            response = {
                                'status': 'success',
                                'message': f'Client {client_name} registered successfully',
                                'timestamp': time.time()
                            }
                        else:
                            response = {
                                'status': 'error',
                                'message': 'Failed to register client',
                                'timestamp': time.time()
                            }
                        
                        client_socket.send(json.dumps(response).encode())
                        continue
                    
                    elif command == 'client_disconnect':
                        client_name = request_data.get('client_name', client_name)
                        break
                    
                    elif not client_identified:
                        error_response = {
                            "error": "Client must identify itself first",
                            "required_command": "client_identification"
                        }
                        client_socket.send(json.dumps(error_response).encode())
                        continue
                    
                    response = self.process_request(request_data, client_name)
                    client_socket.send(json.dumps(response).encode())
                    
                except json.JSONDecodeError:
                    error_response = {"error": "Invalid JSON"}
                    client_socket.send(json.dumps(error_response).encode())
                except Exception as e:
                    error_response = {"error": str(e)}
                    client_socket.send(json.dumps(error_response).encode())
                    
        except Exception as e:
            print(f"Client handler error for {client_name or 'unidentified client'}: {e}")
        finally:
            disconnected_client = self.unregister_client(client_socket, client_name)
            client_socket.close()
    
    def start_logging_thread(self):
        """Start the logging thread"""
        if self.enable_logging:
            try:
                self.can_logging_thread = threading.Thread(target=self.logging_loop, args=('CAN',))
                self.can_logging_thread.daemon = True
                self.can_logging_thread.start()
                print("Started CAN logging thread")
            except Exception as e:
                print(f"Failed to start CAN logging thread: {e}")
                self.error_byte = 0x05
                self.device_byte = 0x00
                self.additional_byte = 0x01
                self.can_send_on_0F7()

            try:
                self.camera_logging_thread = threading.Thread(target=self.logging_loop, args=('CAMERA',))
                self.camera_logging_thread.daemon = True
                self.camera_logging_thread.start()
                print("Started CAMERA logging thread")
            except Exception as e:
                print(f"Failed to start CAMERA logging thread: {e}")
                self.error_byte = 0x05
                self.device_byte = 0x00
                self.additional_byte = 0x04
                self.can_send_on_0F7()

            try:
                self.csi_logging_thread = threading.Thread(target=self.logging_loop, args=('CSI',))
                self.csi_logging_thread.daemon = True
                self.csi_logging_thread.start()
                print("Started CSI logging thread")
            except Exception as e:
                print(f"Failed to start CSI logging thread: {e}")
                self.error_byte = 0x05
                self.device_byte = 0x00
                self.additional_byte = 0x02
                self.can_send_on_0F7()
            
            try:
                self.pm_logging_thread = threading.Thread(target=self.logging_loop, args=('PM',))
                self.pm_logging_thread.daemon = True
                self.pm_logging_thread.start()
                print("Started PM logging thread")
            except Exception as e:
                print(f"Failed to start PM logging thread: {e}")
                self.error_byte = 0x05
                self.device_byte = 0x00
                self.additional_byte = 0x03
                self.can_send_on_0F7()
        else:
            print("Logging not properly configured or not enabled")
            return False
    
    def logging_loop(self, data_type):
        """Main logging loop"""
        print(f"{data_type} logging thread started")
        match data_type:
            case 'CAN':
                columns = self.config.get_columns()
            case 'CAMERA':
                columns = self.config.get_camera_columns()
            case 'CSI':
                columns = self.config.get_csi_columns()
            case 'PM':
                columns = self.config.get_pm_columns()
        serial_number = self.config.get_serial_number()
        log_duration = self.config.get_log_duration()
        directory = self.config.get_directory()
        file_index = 0
        start_time = datetime.now().strftime("%Y_%m_%d_%H%M")
        last_update_time = time.time()
        last_non_nan_values = {key: np.nan for key in columns}

        def write_to_file(dictionary, start_time):
            nonlocal file_index, last_update_time
            non_useful_values = {'Connection_Error', np.nan}
            current_time = time.time()
            if current_time - last_update_time >= log_duration:
                file_index += 1
                last_update_time = current_time
            file_name = f'{directory}{serial_number}_{data_type}_{start_time}_{file_index}.csv'
            if not os.path.exists(file_name):
                with open(file_name, 'w') as f:
                    f.write(','.join(columns) + '\n')
            filtered_values = {str(v) for k, v in dictionary.items() if k != 'time'}
            if not filtered_values.issubset(non_useful_values):
                with open(file_name, 'a') as f:
                    f.write(','.join(str(x) for x in list(dictionary.values())) + '\n')
        
        def convert_to_pascal(value):
            return ((value / 5000.0) * 0.4 - 0.2) * 100000
        
        consecutive_null_cycles = 0
        max_null_cycles = 250

        try:
            while True:
                if data_type == 'PM':
                    with self.sensor_queue_lock:
                        if self.sensor_queue:
                                sensor_data = self.sensor_queue.pop(0)
                                null_dict = dict.fromkeys(columns, np.nan)
                                data_found = False
                                
                                for key in columns:
                                    if key == 'time':
                                        if sensor_data:
                                            first_key = next(iter(sensor_data))
                                            sensor_timestamp = sensor_data[first_key]['timestamp']
                                            formatted_time = datetime.fromtimestamp(sensor_timestamp)
                                            null_dict[key] = formatted_time.strftime("%H:%M:%S.%f")[:-5] + '00'
                                        else:
                                            null_dict[key] = datetime.now().strftime("%H:%M:%S.%f")[:-5] + '00'
                                        continue
                                        
                                    if key in sensor_data:
                                        data_found = True
                                        value = sensor_data[key]['value']
                                        null_dict[key] = value
                                
                                if data_found:
                                    consecutive_null_cycles = 0
                                    print(f'Received {data_type} data: {null_dict}')
                                    write_to_file(null_dict, start_time)
                                else:
                                    consecutive_null_cycles += 1
                        else:
                            consecutive_null_cycles += 1
                            if consecutive_null_cycles >= max_null_cycles:
                                print(f'No {data_type} data for {max_null_cycles} consecutive cycles, stopping logger')
                                break
                        time.sleep(0.05)


                
                else:
                    null_dict = dict.fromkeys(columns, np.nan)
                    
                    if data_type == 'CAN':
                        with self.data_lock:
                            response = {'data': self.can_data.copy()}
                    else:
                        response = {'data': self.client_data.copy()}

                    if response and 'data' in response:
                        can_data = response['data']
                        data_found = False
                        
                        for key in columns:
                            if key == 'time':
                                null_dict[key] = datetime.now().strftime("%H:%M:%S.%f")[:-5] + '00'
                                continue
                                
                            if key in can_data:
                                data_found = True
                                value = can_data[key]['value']
                                
                                if key == "Pressure1" and data_type == 'CAN':
                                    value = convert_to_pascal(value)
                                
                                if key in ["nozzle_clear", "nozzle_blocked", "gravel", "action_object"]:
                                    byte_updates = {}
                                    
                                    if key == "nozzle_clear":
                                        byte_updates["fan_byte"] = {"operation": "update_bits", "value": 0x10, "mask": 0x10}
                                    elif key == "nozzle_blocked":
                                        byte_updates["fan_byte"] = {"operation": "update_bits", "value": 0x20, "mask": 0x20}
                                    elif key == "gravel":
                                        byte_updates["fan_byte"] = {"operation": "update_bits", "value": 0x40, "mask": 0x40}
                                    elif key == "action_object":
                                        byte_updates["fan_byte"] = {"operation": "update_bits", "value": 0x80, "mask": 0x80}
                                    
                                    self.update_can_bytes(byte_updates, f"logging_thread_{data_type}")

                                null_dict[key] = value

                                can_timestamp = can_data[key]['timestamp']
                                formatted_time = datetime.fromtimestamp(can_timestamp)
                                null_dict['time'] = formatted_time.strftime("%H:%M:%S.%f")[:-5] + '00'
                        
                        if data_found:
                            consecutive_null_cycles = 0
                        else:
                            consecutive_null_cycles += 1
                            
                    else:
                        consecutive_null_cycles += 1
                        error = response.get('error', 'No response') if response else 'Connection error'
                        print(f"Error getting data from server: {error} (cycle {consecutive_null_cycles})")

                    # Check if we should exit due to no data
                    if consecutive_null_cycles >= max_null_cycles:
                        print(f'No {data_type} data for {max_null_cycles} consecutive cycles, stopping logger')
                        break

                    # Check if all values except time are NaN
                    if all(pd.isna(null_dict[key]) for key in null_dict if key != 'time'):
                        if consecutive_null_cycles >= max_null_cycles:
                            break
                    else:
                        # Write to file only if we have some data
                        write_to_file(null_dict, start_time)

                    time.sleep(0.1)  # Poll server every 100ms

        except KeyboardInterrupt:
            print("Logging interrupted by user")
        except Exception as e:
            print(f"Error in logging loop: {e}")
        finally:
            print(f"{data_type} logger stopped")
    
    def get_override_state(self):
        """Get the current override state"""
        with self.override_state_lock:
            return self.current_override_state
    
    def get_pm_values(self, sensor_id=None):
        with self.last_pm_values_lock:
            if sensor_id is not None:
                if sensor_id in self.last_pm_values:
                    pm_data = self.last_pm_values[sensor_id]
                    return {
                        'pm_values': {str(sensor_id): pm_data['value']},
                        'timestamp': pm_data['timestamp']
                    }
                else:
                    return None
            else:
                # Return all available PM values
                if self.last_pm_values:
                    pm_values = {}
                    for sid, data in self.last_pm_values.items():
                        pm_values[str(sid)] = data['value']
                    return {
                        'pm_values': pm_values,
                        'timestamp': time.time()
                    }
                else:
                    print("No PM data available")
                    return None


    def start_server(self):
        """Start the Unix domain socket server"""
        # Remove existing socket file if it exists
        if os.path.exists(self.socket_path):
            os.unlink(self.socket_path)
            
        self.server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server_socket.bind(self.socket_path)
        self.server_socket.listen(5)
        
        # Set permissions for the socket
        os.chmod(self.socket_path, 0o666)
        
        self.running = True
        print(f"CAN Server listening on {self.socket_path}")
        print("Available commands: get_all, send_data")
        
        # Now start CAN monitoring
        self.start_monitoring_threads()
        
        # Accept client connections
        while self.running:
            try:
                client_socket, _ = self.server_socket.accept()
                print("New client connected")
                client_thread = threading.Thread(
                    target=self.handle_client, 
                    args=(client_socket,)
                )
                client_thread.daemon = True
                client_thread.start()
            except Exception as e:
                if self.running:
                    print(f"Error accepting connection: {e}")
                    
    def process_request(self, request_data, client_info=None):
        """Process client requests"""
        command = request_data.get('command')
        
        if command == 'get_all':
            with self.data_lock:
                # Combine CAN data and client data
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
        
        elif command == 'update_can_bytes':
            byte_updates = request_data.get('bytes', {})
            
            if not byte_updates:
                return {'error': 'Missing bytes data for update_can_bytes command'}
            
            success = self.update_can_bytes(byte_updates, client_info)
            if success:
                return {
                    'status': 'success',
                    'message': f'CAN bytes updated successfully',
                    'updated_bytes': byte_updates,
                    'timestamp': time.time()
                }
            else:
                return {'error': 'Failed to update CAN bytes'}
                
        elif command == 'send_data':
            key = request_data.get('key')
            value = request_data.get('value')
            
            if key is None or value is None:
                return {'error': 'Missing key or value for send_data command'}
            
            success = self.store_client_data(key, value, client_info)
            if success:
                #print(f"SERVER: Storing data from {client_info or 'unknown client'} - {key} = {value}")
                return {
                    'status': 'success',
                    'message': f'Data stored successfully: {key} = {value}',
                    'key': key,
                    'value': value,
                    'timestamp': time.time()
                }
            else:
                return {'error': 'Failed to store data'}
            
        elif command == 'update_fps':
            fps_type = request_data.get('fps_type')
            fps_value = request_data.get('fps')
            if fps_value is None:
                return {'error': 'Missing FPS value for update_fps command'}
            
            with self.can_bytes_lock:
                if fps_type == 'nn':
                    self.nn_fps = fps_value
                elif fps_type == 'front_csi':
                    self.front_csi_fps = fps_value
                elif fps_type == 'rear_csi':
                    self.rear_csi_fps = fps_value

            return {
                'status': 'success',
                'message': f'FPS updated successfully to {fps_value}',
                'timestamp': time.time()
            }

        elif command == 'send_0F7':
            success = self.can_send_on_0F7()
            if success:
                return {
                    'status': 'success',
                    'message': 'CAN message 0x0F7 sent successfully',
                    'sent_data': {
                        'error_byte': self.error_byte,
                        'device_byte': self.device_byte,
                        'additional_byte': self.additional_byte
                    },
                    'timestamp': time.time()
                }
            else:
                return {'error': 'Failed to send CAN message 0x0F7'}

        elif command == 'send_1F7':
            #success = self.can_send_on_1F7()
            if success:
                return {
                    'status': 'success',
                    'message': 'CAN message 0x1F7 sent successfully',
                    'sent_data': {
                        'status_byte': self.status_byte,
                        'camera_byte': self.camera_byte,
                        'nozzle_byte': self.nozzle_byte,
                        'gps_byte': self.gps_byte,
                        'fan_byte': self.fan_byte,
                        'fps_byte': self.fps_byte
                    },
                    'timestamp': time.time()
                }
            else:
                return {'error': 'Failed to send CAN message 0x1F7'}
        
        elif command == 'start_logging':
                self.enable_logging = True
                self.start_logging_thread()
                return {
                    'status': 'success',
                    'message': 'Logging started with auto-configuration',
                    'columns': len(self.log_columns) if hasattr(self, 'log_columns') else 0,
                    'timestamp': time.time()
                }
                
        elif command == 'stop_logging':
            self.enable_logging = False
            return {
                'status': 'success',
                'message': 'Logging stopped',
                'timestamp': time.time()
            }

        elif command == 'update_camera_status':
            camera_name = request_data.get('camera')
            if camera_name == 'front':
                self.front_camera_last_active = time.time()
            elif camera_name == 'rear':
                self.rear_camera_last_active = time.time()
            elif camera_name == 'primary_nozzle':
                self.primary_camera_last_active = time.time()
            elif camera_name == 'secondary_nozzle':
                self.secondary_camera_last_active = time.time()

            return {
                'status': 'success',
                'message': 'Camera updated successfully',
                'timestamp': time.time()
            }

        elif command == 'get_override_state':
            return {
                'status': 'success',
                'override_state': self.get_override_state(),
                'timestamp': time.time()
            }
        
        elif command == 'get_pm_values':
            pm_values = self.get_pm_values(sensor_id=request_data.get('sensor_id'))
            return {
                'status': 'success',
                'pm_values': pm_values['pm_values'] if pm_values else {},
                'timestamp': time.time()
            }

        elif command == 'get_sd_usage':
            return {
                'status': 'success',
                'sd_usage': self.sd_card_full_flag,
                'timestamp': time.time()
            }
                
    def stop_server(self):
        """Stop the server"""
        print("Stopping CAN server...")
        self.running = False
        if self.server_socket:
            self.server_socket.close()
        if os.path.exists(self.socket_path):
            os.unlink(self.socket_path)
        print("CAN Server stopped")

if __name__ == '__main__':
    server = CanServer()
    try:
        server.start_server()
    except KeyboardInterrupt:
        print("Shutting down CAN server...")
        server.stop_server()