import yaml
import cantools
import subprocess
import re

'''
class Configuration:
    def __init__(self, filename='config.yaml'):
        with open(filename, 'r') as file:
            self.config = yaml.safe_load(file)

    def get(self, key):
        return self.config.get(key)
    
    def get_camera_columns(self):
        return self.get('signal_settings').get('camera_signals')
    
    def get_can_signals(self):
        return self.get('signal_settings').get('can_signals')
    
    def get_columns(self):
        signal_settings = self.get('signal_settings')
        can_signals = signal_settings.get('can_signals')
        ai_signals = signal_settings.get('ai_signals')
        pm_signals = signal_settings.get('pm_signals')
        return can_signals + ai_signals + pm_signals
    
    def get_directory(self):
        print(self.get('logging_settings')[2].get('logged_data_dir'))
        return self.get('logging_settings')[2].get('logged_data_dir')
    
    def get_log_duration(self):
        return self.get('logging_settings')[1].get('max_log_duration')
    
    def get_pm_columns(self):
        return self.get('signal_settings').get('pm_signals')
    
    def get_serial_number(self):
        return self.get('vehicle_info')[0].get('serial_number')

    def get_dbc_file(self):
        return cantools.database.load_file(self.get('logging_settings')[4].get('logged_data_dir'))
'''

class Configuration:
    def __init__(self, filename='/mnt/ssd/csi_pipeline/config/logging_config.yaml'):
        with open(filename, 'r') as file:
            self.config = yaml.safe_load(file)

    def get(self, key):
        return self.config.get(key)
    
    def get_camera_columns(self):
        return self.get('signal_settings').get('camera_signals')
    
    def get_can_signals(self):
        return self.get('signal_settings').get('can_signals')
    
    def get_columns(self):
        signal_settings = self.get('signal_settings')
        can_signals = signal_settings.get('can_signals')
        return can_signals
    
    def get_directory(self):
        return self.get('logging_settings')[2].get('logged_data_dir')
    
    def get_log_duration(self):
        return self.get('logging_settings')[1].get('max_log_duration')
    
    def get_pm_columns(self):
        return self.get('signal_settings').get('pm_signals')
    
    def get_serial_number(self):
        return self.get('vehicle_info')[0].get('serial_number')
    
    def get_csi_columns(self):
        return self.get('signal_settings').get('csi_signals')

    #def get_dbc_file(self):
    #    return cantools.database.load_file(self.get('logging_settings')[4].get('logged_data_dir'))

    def get_camera_id(self, camera_name):
        camera_info = self.get('camera_info')
        for camera in camera_info:
            if camera_name in camera:
                return camera[f'{camera_name}'][0]['id']
        else:
            return None
    
    def get_video_device(self, camera_id):
        """Get the /dev/video* information for the camera with the given id."""
        # Run the v4l2-ctl --list-devices command
        result = subprocess.run(['v4l2-ctl', '--list-devices'], capture_output=True, text=True)

        # Split the output into lines
        lines = result.stdout.splitlines()
        for i, line in enumerate(lines):
            if camera_id in line:
                return lines[i + 1].strip()
                

        # If the /dev/video* information was not found
        return None
