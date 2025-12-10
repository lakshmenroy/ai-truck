import json
import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst
import logging
import subprocess
import shlex
import os
import datetime


import time
start_time=time.time()
frame_count=0

"""

The GETFPS class is from nvidia 

################################################################################
# Copyright (c) 2019-2020, NVIDIA CORPORATION. All rights reserved.
#
# Permission is hereby granted, free of charge, to any person obtaining a
# copy of this software and associated documentation files (the "Software"),
# to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense,
# and/or sell copies of the Software, and to permit persons to whom the
# Software is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.  IN NO EVENT SHALL
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
# DEALINGS IN THE SOFTWARE.
################################################################################


"""
class GETFPS:
    def __init__(self,stream_id):
        global start_time
        self.start_time=start_time
        self.is_first=True
        global frame_count
        self.frame_count=frame_count
        self.stream_id=stream_id
        self.current_fps = None
    def get_fps(self):
        end_time=time.time()
        if(self.is_first):
            self.start_time=end_time
            self.is_first=False
        if(end_time-self.start_time>5):
            # print("**********************FPS*****************************************")
            # print("Fps of stream",self.stream_id,"is ", float(self.frame_count)/5.0)
            self.current_fps = int(float(self.frame_count)/5.0)
            self.frame_count=0
            self.start_time=end_time
        else:
            self.frame_count=self.frame_count+1

        return self.current_fps

    def print_data(self):
        print('frame_count=',self.frame_count)
        print('start_time=',self.start_time)



class Config:
    def __init__(self, config_file):
        # initial state
        self.cameras = None
        self.sinks = None
        # self.file_paths = []
        self.socket_path = None
        # self.output_format = None
        self.metadata_source = None
        self.log_level = "DEBUG"
        self.display_height = 1080
        self.display_width = 1920
        self.log_frame_height = 1080
        self.log_frame_width = 1920
        self.log_frame_rate = 30
        self.need_long_format_logs = False
        self.test_frame_count = 10
        self.perform_frame_capture_test = False
        self.send_v4l2_ctl_settings = False
        self.status_json_path = "/tmp/bucher_ai_camera_status_on_boot_{%Y%m%d%H%M}.json"
        self.export_status_json = False
        
        try:
            with open(config_file) as f:
                data = json.load(f)

            self.cameras = data['cameras']
            self.sinks = data['sinks']
            # self.file_paths = data['file_paths']
            self.socket_path = data['socket_path']    
            # self.output_format = data['output_format']
            self.metadata_source = data['metadata_sources']
            self.log_level = data['logging_level']
            self.display_height = data['display_height']
            self.display_width = data['display_width']
            self.log_frame_height = data['log_frame_height']
            self.log_frame_width = data['log_frame_width']
            self.log_frame_rate = data['log_frame_rate']
            self.need_long_format_logs = data['enable_long_format_logging_output']
            self.test_frame_count = data['test_frame_count']
            self.perform_frame_capture_test = data['perform_frame_capture_test']
            self.send_v4l2_ctl_settings = data['send_v4l2_ctl_settings']
            self.status_json_path = data['status_json_path']
            self.export_status_json = data['export_status_json']

            # mapping boolean values to decimal
            for camera in self.cameras:
                camera['vertical_flip'] = abs(int(camera['vertical_flip']))
                camera['horizontal_flip'] = abs(int(camera['horizontal_flip']))
                camera['sensor_mode'] = abs(int(camera['sensor_mode']))
                camera['gmsl_port'] = abs(int(camera['gmsl_port']))


            # mapping from device id to camera config
            # self.config_mapped_by_device_tree_id = {camera['device_tree_index']: camera for camera in self.cameras}

            # mapping from device id to the list index of self.cameras
            # self.camera_index_mapped_by_device_tree_node_id = {camera['device_tree_node_id']: index for index, camera in enumerate(self.cameras)}

            # print(self.config_mapped_by_device_tree_id)
            # print(self.camera_index_mapped_by_device_tree_node_id)
        except Exception as e:
            print("Error reading config file", e)
            raise e



class AppContext:
    def __init__(self, config):
        self.pipeline_state = Gst.State.NULL
        self.active_sinks = []
        self.active_sources = []
        self.metadata = {}
        self.logger = None
        self._state = config
        self._main_process_pid = None

        # self.initialise_logging()
        # self.initialise_cameras()
        # self.export_status_json()

        # export the status to a json file
        # if self._state.status_json_path is not None and self._state.export_status_json:
        #     self.export_status_json()

    def initialise_logging(self):

        self.logger = logging.getLogger('app')
        log_level = getattr(logging, self._state.log_level.upper())
        self.logger.setLevel(log_level)
        # print("Setting logging level to", log_level)
        console_handler = logging.StreamHandler()

        if self._state.need_long_format_logs:
            formatter = logging.Formatter('%(asctime)s|%(name)s|%(levelname)s|%(filename)s:%(lineno)d (%(funcName)s): %(message)s')
        else:
            formatter = logging.Formatter('%(levelname)s: %(message)s')

        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)

        
    @property    
    def state(self):
        """
        The state property.
        """
        return self._state
    
    @property
    def main_process_pid(self):
        """
        returns the main process pid
        """
        return self._main_process_pid
    
    @main_process_pid.setter
    def main_process_pid(self, pid):
        self._main_process_pid = pid
        self.logger.debug(f"Main process pid updated to {pid}")
        # notify observers about the main process pid change
        # self.notify_observers()

    def initialise_cameras(self):
        """"
        1. finds how many cameras are connected and what are their device ids
        2. checks the config file and matches the camera physical port number wit the detected device id

        first we find out what video devices are available with `v4l2-ctl --list-devices | grep video | awk '{print $1}'` or listing 
        the "/sys/devices/platform/tegra-capture-vi/video4linux/" directory
        """

        """
        in the begining we assmume no cameras are detected, we introduce a new binary field to the self.config.cameras called detected_on_init and set it to False
        """
        for camera in self._state.cameras:
            camera['detected_on_init'] = False

        v4l2_ctl_command = "/usr/bin/v4l2-ctl --list-devices | /usr/bin/grep video | /usr/bin/awk '{print $1}'"

        camera_index_mapped_by_device_tree_node_id = {camera['device_tree_node_id']: index for index, camera in enumerate(self._state.cameras)}

        try:
            # communicate eith the pipe using a context manager for resource management
            with subprocess.Popen(v4l2_ctl_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True) as process:
                (output, error) = process.communicate()

            if error:
                self.logger.error(f"Error getting video devices: {error}")
                raise Exception(error)

            # Decode the byte string to a regular string (assuming UTF-8 encoding)
            output = output.decode('utf-8')
            devices = output.strip().split('\n')

            for device in devices:
                # print(device)
                # now we go through the configs cameras to set the device path field, 
                udevadm_command = "/usr/bin/udevadm info --query=all {0}".format(device)
                try:
                    # udevadm_command = ["udevadm", "info", "--query=all", device]
                    with subprocess.Popen(udevadm_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True) as udevadm_process:
                        (udevadm_output, udevadm_error) = udevadm_process.communicate()

                    if udevadm_error:
                        self.logger.error(f"Error getting udev info for device {device}: {udevadm_error}")
                        continue

                    if udevadm_process.returncode != 0:
                        self.logger.error(f"Error getting udev info for device {device}")
                        continue

                    # Decode the byte string to a regular string (assuming UTF-8 encoding)
                    udevadm_output = udevadm_output.decode('utf-8')
                    for line in udevadm_output.strip().split('\n'):
                        if 'ID_V4L_PRODUCT' in line:
                            device_tree_node_id = line.split('=')[1]
                            # product is the last part of the string
                            device_tree_node_id = device_tree_node_id.split(' ')[-1]
                            self.logger.info(f"Detected device {device} with id {device_tree_node_id}")
                            # print(f"Detected device {device} with product {device_tree_node_id}")
                            # self.config.config_mapped_by_device_tree_id[device_tree_node_id]['device_path'] = device
                            self._state.cameras[camera_index_mapped_by_device_tree_node_id[device_tree_node_id]]['device_path'] = device
                            # now we set the detected_on_init field to True
                            self._state.cameras[camera_index_mapped_by_device_tree_node_id[device_tree_node_id]]['detected_on_init'] = True
                            break

                except Exception as e_udev:
                    self.logger.error(f"Error getting udev info for device {device}: {e_udev}, maybe divice tree id {e_udev} --> {device} is not listed in the config file?")
                    continue
                
        except Exception as e_dev:
            self.logger.error(f"Error getting video devices: {e_dev}")
            raise e_dev
        
        # we check if at least one camera was detected, if detected setup v4l2-ctl else raise an exception
        if any(camera['detected_on_init'] for camera in self._state.cameras):
            # set v4l2-ctl for each camera
            for camera_index, camera in enumerate(self._state.cameras):
                if camera['detected_on_init']:
                    try:
                        camera['capture_test_passed'] = None
                        camera['v4l2_settings_sent']  = None

                        if self._state.perform_frame_capture_test:
                            self.test_v4l2_ctl_frame_retrival(camera_index, camera['device_path'], self._state.test_frame_count)

                        if self._state.send_v4l2_ctl_settings:
                            self.set_v4l2_ctl(camera_index, camera['device_path'], camera['sensor_mode'], camera['vertical_flip'], camera['horizontal_flip'])

                        pass

                    except Exception as e_v4l2:
                        self.logger.error(f"Error from capture test or setting v4l2-ctl for device {camera['device_path']}: {e_v4l2}")
                        continue
        else:
            self.logger.error(f"No cameras detected on init")
            raise Exception("No cameras detected on init")
        

        

        
    def test_v4l2_ctl_frame_retrival(self, camera_index, device_path, test_frame_count=10):
        """
        tests the v4l2-ctl command for frame retrival
        """
        frame_retrival_test_command = f"/usr/bin/v4l2-ctl -d {device_path} --stream-mmap --stream-count={test_frame_count:0d}"
        frame_retrival_test_command_args = shlex.split(frame_retrival_test_command)

        #     process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=1, close_fds=True, universal_newlines=True)

        TIMEOUT_COMMUNICATE = 5.0

        try:
            # Execute the command
            frame_retrival_test_process = subprocess.Popen(frame_retrival_test_command_args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=1, close_fds=True, universal_newlines=True, shell=False)
            self.logger.debug(f"sending test capture command: {frame_retrival_test_command} | pid = {frame_retrival_test_process.pid}")

            # communicate with the process with tha timeout
            try:
                (output, error) = frame_retrival_test_process.communicate(timeout=TIMEOUT_COMMUNICATE)  # Set the timeout value in seconds

                if output:
                    # output = output.decode('utf-8')
                    self.logger.debug(f"output (test capture): {output}")

                if error:
                    # error = error.decode('utf-8')
                    # parse the error into a string and count the number of '<'s to get the number of frames captured
                    frames_string = error.strip()
                    num_frames = frames_string.count('<')
                    self.logger.debug(f"captured {num_frames} frames from {device_path}")

                    if num_frames == test_frame_count:
                        self.logger.debug(f"passed capture test ({device_path}|{self._state.cameras[camera_index]['name']}): {output}")
                        self._state.cameras[camera_index]['capture_test_passed'] = True
                        return 0

                    else:
                        self.logger.error(f"Error executing v4l2-ctl (test capture): {error}")
                        self._state.cameras[camera_index]['capture_test_passed'] = False
                        return -1
                    
            except subprocess.TimeoutExpired:
                # Handle timeout error here
                print(f"Timeout ({TIMEOUT_COMMUNICATE} seconds) occurred while waiting response from {frame_retrival_test_command}, sending SIGINT to process {frame_retrival_test_process.pid}")
                frame_retrival_test_process.send_signal(subprocess.signal.SIGINT) 
                # frame_retrival_test_process.kill() # Kill the process if it exceeds the timeout
                frame_retrival_test_process.wait()
                self.logger.debug(f"process return code: {frame_retrival_test_process.returncode}, pid: {frame_retrival_test_process.pid}")
                return -2
          
        
        except Exception as e:
            self.logger.error(f"An unexpected error occurred: {e}")
            return -2
            
        

    def set_v4l2_ctl(self, camera_index, device_path, sensor_mode=3, vertical_flip=1, horizontal_flip=0):
        """
        sets the `"v4l2-ctl -d /dev/video%d --stream-mmap --set-fmt-video width=800,height=800 --stream-count=1 -c vertical_flip=1,horizontal_flip=0,hdr_enable=1,sensor_mode=3,bypass_mode=0", sensor_id` using a command
        """
        
        v4l2_ctl_settings_update_command = f"/usr/bin//v4l2-ctl -d {device_path}"\
                  f" -c vertical_flip={vertical_flip},horizontal_flip={horizontal_flip},hdr_enable=1,sensor_mode={sensor_mode},bypass_mode=0"
        
        # set the v4l2_settings_sent flag to False
        self._state.cameras[camera_index]['v4l2_settings_sent'] = False
        TIMEOUT_COMMUNICATE = 5.0

        
        # Execute the command with a timeout (this is the blocking approach, if this fails try what we did test capture above with polling and SIGINTing the process)
        try:
            v4l2_ctl_settings_update_process = subprocess.Popen(shlex.split(v4l2_ctl_settings_update_command), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                self.logger.debug(f"Executing command: {v4l2_ctl_settings_update_command} | pid = {v4l2_ctl_settings_update_process.pid}")
                (output, error) = v4l2_ctl_settings_update_process.communicate(timeout=TIMEOUT_COMMUNICATE)  # Set the timeout value in seconds

                output = output.decode('utf-8')
                error = error.decode('utf-8')

                if error:
                    self.logger.error(f"Error executing v4l2-ctl: {error}")
                    raise Exception(f"Error executing v4l2-ctl: {error}")
                else:
                    # print(f"Command executed successfully: {output}")
                    self._state.cameras[camera_index]['v4l2_settings_sent'] = True
                    # process return code
                    self.logger.debug(f"process return code: {v4l2_ctl_settings_update_process.returncode}, pid: {v4l2_ctl_settings_update_process.pid}")
                    pass

            except subprocess.TimeoutExpired as err_timeout:

                v4l2_ctl_settings_update_process.kill()  # Kill the process if it exceeds the timeout
                self.logger.error(f"Timeout ({TIMEOUT_COMMUNICATE} secs) occurred while executing v4l2-ctl: {err_timeout}, killing process {v4l2_ctl_settings_update_process.pid}, retuncode = {v4l2_ctl_settings_update_process.returncode}")
                # process return code
                raise err_timeout
                

        except Exception as err_:
            # Handle errors in the subprocess
            self.logger.error(f"An error occurred while executing v4l2-ctl: {err_}")
            raise err_
        

    def export_status_json(self):
        """
        exports the current state to a json file
        """
        if self._state.status_json_path is None or self._state.export_status_json is False:
            self.logger.debug(f"Status export is not provisioned in the config file. Skipping status export.")
            return

        status_json_path = self._state.status_json_path
        status_json_path = datetime.datetime.now().strftime(status_json_path)
        self.logger.debug(f"Exporting status to {status_json_path}")
        # self.logger.debug(f"State: {state_jason}")

        # if the file exists, we delete it
        if os.path.exists(status_json_path):
            try:
                os.remove(status_json_path)
                self.logger.debug(f"Deleted existing status file {status_json_path}")
            except Exception as e:
                self.logger.error(f"Error deleting existing status file {status_json_path}: {e}")
                return
        # export the status to a json file, while filtering out unserialisable objects
        try:
            with open(status_json_path, 'w') as f:
                state_dictified = self._state.__dict__
                # remove the logger object from the state_json as it is not serialisable
                state_dictified.pop('logger', None)
                # create state_json from state_dictified
                state_json = json.dumps(state_dictified, indent=4)
                f.write(state_json)
                self.logger.debug(f"Status exported to {status_json_path}")
        except Exception as e:
            self.logger.error(f"Error exporting status to {status_json_path}: {e}")


if __name__ == "__main__":

    cfg = Config("pipeline_config.json")
    ctx = AppContext(cfg)

 
    # # print evertthing on ctx
    # print(ctx.__dict__)

    # # print evertthing on ctx.state
    # print(ctx.state.__dict__)

    # print(ctx.state.socket_path)


