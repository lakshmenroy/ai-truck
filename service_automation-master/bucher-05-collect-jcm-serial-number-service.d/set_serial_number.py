
"""
    Every time the device is rebooted, this script reads and decodes the serial number sent from the JVM and saves it in the config file.

    Author: Bouchra Mohamed Lemine
"""

import os
import can
import cantools
from can.interface import Bus
import yaml
from yaml.loader import SafeLoader
import sys
from ruamel.yaml import YAML
import sys



def set_serial_number(config_data):
    """
        The main function that reads the truck's serial number from the telematics bus and saves it.
    """

    can.rc['interface'] = 'socketcan'
    can.rc['channel'] = 'can0'
    can.rc['bitrate'] = 250000
    can.rc['can_filters'] = [{"can_id": 0x205, "can_mask": 0xFFF, "extended": False}]


    # Create a CAN message decoder using the DBC file.
    db = cantools.database.load_file('/mnt/ssd-1/workspace/jetson-deepstream/bscripts/logging/logged_can_signals_25_07_2023.DBC')  

    bus = Bus()

    while True:
        # Try to read the CAN message that contains the serial number.
        msg = bus.recv()
        try:        
            # Decode and save the serial number.
            serial_number = db.decode_message(msg.arbitration_id, msg.data)
            serial_number = serial_number['EQ_number_high_order'] * 65536 + serial_number['EQ_number_mid_order'] * 256 + serial_number['EQ_number_low_order']
            with open(config_file, "w") as yamlfile:
                config_data['vehicle_info'][0]['serial_number'] = f'SN{serial_number}'
                yaml.dump(config_data, yamlfile)
                yamlfile.close()

                break
            
        except Exception as e:
            # print(e)
            pass

        

if __name__ == '__main__':

    config_file = "/mnt/ssd-1/workspace/jetson-deepstream/bscripts/logging/logging_config.yaml"

    yaml = YAML()
    yaml.explicit_start = True
    yaml.indent(offset=3)
    yaml.preserve_quotes = True  
    
    with open(config_file, "r") as yamlfile:
        data = yaml.load(yamlfile)

        # If the serial number is not already set in the config file, set it.
        if not data['vehicle_info'][0]['serial_number']:
            set_serial_number(data)
            
        yamlfile.close()

    sys.exit(0)

 

 
