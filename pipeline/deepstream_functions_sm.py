"""
Author: Freddie Clarke | Bucher Municipal
Date: 2024-03-12
"""

import sys

sys.path.append('../')
import gi

gi.require_version('Gst', '1.0')
import pyds
from gi.repository import Gst
from enum import Enum
from datetime import datetime
import time
import os
from utils import Configuration
from can_subsystem import can_send_on_1F7

config = Configuration()
serial_number = config.get_serial_number()
log_duration = config.get_log_duration()
columns = config.get_camera_columns()
directory = config.get_directory()
last_update_time = None
file_index = 0

video_start_time = datetime.now().strftime("%H:%M:%S")
file_start_time = datetime.now().strftime("%Y_%m_%d_%H%M")

CAN_ENABLED = True

if CAN_ENABLED:
    from can_state_machine import SmartStateMachine
    SSM = SmartStateMachine()

class DETECTION_CATEGORIES(Enum):
    PGIE_CLASS_ID_BACKGROUND = 0
    PGIE_CLASS_ID_ACTION_OBJECT = 1
    PGIE_CLASS_ID_EMPTY = 2
    PGIE_CLASS_ID_CHECK_NOZZLE = 2
    PGIE_CLASS_ID_GRAVEL = 3
    PGIE_CLASS_ID_NOZZLE_BLOCKED = 4
    PGIE_CLASS_ID_NOZZLE_CLEAR = 5
    

def nozzlenet_src_pad_buffer_probe(pad, info, u_data, fps_counter_, search_item_list_):
    global CAN_ENABLED

    start_time = file_start_time

    def write_to_file(dictionary, start_time):
        global last_update_time, file_index, directory   
        if last_update_time is None:
            last_update_time = time.time()
        current_time = time.time()
        if current_time - last_update_time >= log_duration:  # 20 minutes = 1200 seconds
            file_index += 1
            last_update_time = current_time
        file_name = f'{directory}{serial_number}_CAMERA_{start_time}_{file_index}.csv'
        if not os.path.exists(file_name):
            with open(file_name, 'w') as f:
                f.write(','.join(columns))
        with open(file_name, 'a') as f:
            f.write('\n' + ','.join(str(x) for x in list(dictionary.values())))

    prediction_dict = dict.fromkeys(columns, 0.0)

    gst_buffer = info.get_buffer()

    if not gst_buffer:
        sys.stderr.write("unable to get pgie src pad buffer\n")
        return

    frame_number = 0

    batch_meta = pyds.gst_buffer_get_nvds_batch_meta(hash(gst_buffer))
    l_frame = batch_meta.frame_meta_list # because our our bach size is 1 we have only one frame 
    frame_meta = pyds.NvDsFrameMeta.cast(l_frame.data)
    ndetections = frame_meta.num_obj_meta
    l_obj = frame_meta.obj_meta_list
    frame_number = frame_meta.frame_num

    obj_id = 0
    deleted = 1
    increment  = True

    nozzle_clear_flag = False
    nozzle_blocked_flag = False
    nozzle_check_flag = False
    action_object_flag =  False

    nozzle_status_string = ""
    action_object_string = None

    fps_count = fps_counter_.get_fps()
    if fps_count:
        print(f'FPS = {fps_count}')
    display_meta = pyds.nvds_acquire_display_meta_from_pool(batch_meta)
    display_meta.num_labels = 1
    py_nvosd_text_params = display_meta.text_params[0]


    highest_confidence = 0.0

    nozzle_status_string = None
    action_object_string = None

    while l_obj is not None:
        try:
            obj_meta = pyds.NvDsObjectMeta.cast(l_obj.data)
        except StopIteration:
            break

        try:
            l_obj = l_obj.next
        except StopIteration:
            break

        if obj_meta.class_id not in search_item_list_ :
            print('class id = ', obj_meta.class_id)
            print('search item list = ', search_item_list_)
            pyds.nvds_remove_obj_meta_from_frame(frame_meta, obj_meta)
            print(f"class = {obj_meta.class_id} object deleted , total deleted = {deleted}")
            deleted += 1

            obj_id += 1
            continue # this will reset the while loop
	
        if obj_meta.class_id == DETECTION_CATEGORIES.PGIE_CLASS_ID_NOZZLE_CLEAR.value:
            nozzle_status_string= "clear"
            obj_meta.rect_params.border_color.set(0.1411, 0.8019, 0.3254, 0.9)
            prediction_dict["nozzle_clear"] = 1.0

        elif obj_meta.class_id == DETECTION_CATEGORIES.PGIE_CLASS_ID_NOZZLE_BLOCKED.value:
            nozzle_status_string = "blocked"
            obj_meta.rect_params.border_color.set(1.0, 0.3764, 0.2156, 0.9)
            prediction_dict["nozzle_blocked"] = 1.0
            
        elif obj_meta.class_id == DETECTION_CATEGORIES.PGIE_CLASS_ID_CHECK_NOZZLE.value:
            nozzle_status_string = "check"
            obj_meta.rect_params.border_color.set(0.96078431, 0.57647059, 0.19215686, 0.9)
            prediction_dict["check_nozzle"] = 1.0
            
        elif obj_meta.class_id == DETECTION_CATEGORIES.PGIE_CLASS_ID_GRAVEL.value:
            nozzle_status_string = "gravel"
            obj_meta.rect_params.border_color.set(0.678, 0.847, 0.902, 0.9)
            prediction_dict["gravel"] = 1.0

        elif obj_meta.class_id == DETECTION_CATEGORIES.PGIE_CLASS_ID_ACTION_OBJECT.value:
            action_object_string = "true"
            obj_meta.rect_params.border_color.set(1.0, 0.0, 0.48627451, 0.9)
            prediction_dict["action_object"] = 1.0

        obj_meta.rect_params.border_width = 5

        if obj_meta.confidence > highest_confidence:
            highest_confidence = obj_meta.confidence

    if CAN_ENABLED:
        SSM.status_send(recieved_ns=nozzle_status_string, recieved_aos=action_object_string)
        SSM.can_send()

    timenow = datetime.now()
    py_nvosd_text_params.display_text = "Frame Number={} \nFPS {} \nNum detection in frame =  {}\nMax Confidence = {:.2f}\nNozzle status = {}\nAction object = {}\nNozzle CAN = {}\nFan CAN = {}\nTime = {}\nSM Current Status = {}\nSM Current State = {}\nSMS Time Difference = {:.3f}\nAction Object Status = {}\nAction Object Diffrence = {:.3f}".format(
                                                                                                        frame_number, 
                                                                                                        fps_count,
                                                                                                        ndetections,
                                                                                                        highest_confidence, 
                                                                                                        nozzle_status_string,
                                                                                                        action_object_string,
                                                                                                        SSM.get_nozzle_state(),
                                                                                                        SSM.get_fan_speed(),
                                                                                                        timenow,
                                                                                                        SSM.get_current_status(),
                                                                                                        SSM.get_current_state(),
                                                                                                        SSM.get_time_difference(),
                                                                                                        SSM.get_action_object_status(),
                                                                                                        SSM.get_action_object_difference())

    # Now set the offsets where the strings should appear
    py_nvosd_text_params.x_offset = 1
    py_nvosd_text_params.y_offset = 1

    # font, color and size
    py_nvosd_text_params.font_params.font_name = "Serif"
    py_nvosd_text_params.font_params.font_size = 1
    # set(red, green, blue, alpha): Set to black
    py_nvosd_text_params.font_params.font_color.set(1.0, 1.0, 1.0, 1.0)

    # Text background color 
    py_nvosd_text_params.set_bg_clr = 1
    # set(R,G,B,Alpha) 
    py_nvosd_text_params.text_bg_clr.set(0.0, 0.0, 0.0, 0.75)
    # using pyds.get_string() to get display_text as string

    pyds.nvds_add_display_meta_to_frame(frame_meta, display_meta)

    prediction_dict["time"] = f'{datetime.now().strftime("%H:%M:%S.%f")[:-5]}00'
    write_to_file(prediction_dict, start_time)

    return Gst.PadProbeReturn.OK
