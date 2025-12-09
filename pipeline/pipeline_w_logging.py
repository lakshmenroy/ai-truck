"""
Note:

## Running the script

This script uses drmsink, if you have desktop manager running stop it using the following command
1. `sudo systemctl stop gdm`
2.  then unset the display variable (DISPLAY=:) using `unset DISPLAY` or `export DISPLAY=`

otherwise use a display manager friendly sink

## Configuring the camera

sensor modes:
---------------------------------------
Mode    Pixel Format    Resolution    FPS
---------------------------------------
0        RGGB @ 12bpp    1936x1096    30
1        RGGB @ 12bpp    1936x1096    30
2        RGGB @ 12bpp    1936x1096    30
3        RGGB @ 20bpp*    1936x1096    30

*20bpp is achieved through PWL compression on the IMX390 sensor, and decompression (12bpp -> 20bpp) on the Jetson.

Streaming may fail without setting the mode and resolutions explicitly.
The sensor mode can be set from v4l2-ctl as follows. The value of n is shown in the mode table for
each sensor. For example, sensor mode 0 would be:

setting sensor mode using v4l2-ctl
v4l2-ctl -csensor_mode=0 --set-fmt-video width=800,height=800,
pixelformat=0

example pipeine
1 v4l2-ctl -csensor_mode=0 # set mode first
2 gst-launch-1.0 nvarguscamerasrc sensor-mode=0 ! "video/x-raw(memory:
NVMM),width=1

Additional Note:
After streaming with Argus (nvarguscamerasrc, argus_camera, nvgstcapture, etc.), stream-
ing frames from V4L2 will no longer work. Adding bypass_mode=0 to the command line flags, as
shown in the example given below will allow streaming frames through V4L2 again. Alternately, re-
booting the system has the same effect.

v4l2-ctl --set-ctrl bypass_mode=0 --stream-mmap ...

v4l2-ctl -d /dev/video%d --stream-mmap --stream-count=1 -c vertical_flip=1,horizontal_flip=0,hdr_enable=1,sensor_mode=3,bypass_mode=0", config->camera_csi_sensor_id

Author: Ganindu Nanayakkara

docs: https://docs.nvidia.com/metropolis/deepstream-archive.html (deepstream 6.2)

"""

import signal
import sys
sys.path.append('../')
sys.path.append('/home/ganindu/.pyenv/versions/PY38-TEST/lib/python3.8/site-packages')
sys.path.append('/home/ganindu/.pyenv/versions/PY38-TEST/lib/python3.8/site-packages/torch2trt-0.4.0-py3.8.egg/')
sys.path.append('/home/ganindu/.pyenv/versions/PY38-TEST/lib/python3.8/site-packages/torchvision-0.15.1a0+42759b1-py3.8-linux-aarch64.egg')
sys.path.append('/home/ganindu/.pyenv/versions/PY38-TEST/lib/python3.8/site-packages/pillow-10.3.0-py3.8-linux-aarch64.egg/')
sys.path.append('/home/ganindu/.pyenv/versions/PY38-TEST/lib/python3.8/site-packages/requests-2.31.0-py3.8.egg/')
sys.path.append('/mnt/ssd/csi_pipeline/')
sys.path.append('/mnt/ssd/')
import gi
gi.require_version('Gst', '1.0')
import os
import pyds
import time
import subprocess
import os.path
import inspect
import socket
import threading
import json
import glob
import numpy as np
import yaml
import time as naptime
from gi.repository import GObject, Gst, GLib
from datetime import datetime
from app_context import Config, AppContext, GETFPS
from gst_helper_functions import make_bucher_ds_filesrc, make_element, link_request_srcpad_to_static_sinkpad, link_static_srcpad_pad_to_request_sinkpad, modify_deepstream_config_files
from enum import Enum
from utils import Configuration
from can_state_machine import SmartStateMachine
from can_client import CanClient
from csi.utils.probes.probe_functions import compute_csi_buffer_probe

class DETECTION_CATEGORIES(Enum):
    PGIE_CLASS_ID_BACKGROUND = 0
    PGIE_CLASS_ID_ACTION_OBJECT = 1
    PGIE_CLASS_ID_EMPTY = 2
    PGIE_CLASS_ID_CHECK_NOZZLE = 2
    PGIE_CLASS_ID_GRAVEL = 3
    PGIE_CLASS_ID_NOZZLE_BLOCKED = 4
    PGIE_CLASS_ID_NOZZLE_CLEAR = 5

Gst.init(None)

sys.path.append('./mw_csi_pkg/csi')
sys.path.append('/opt/nvidia/deepstream/deepstream/lib')
os.environ['GST_DEBUG_DUMP_DOT_DIR'] = '/mnt/syslogic_sd_card'
os.environ['SCRIPT_EXECUTION_DIR'] = os.path.dirname(os.path.realpath(__file__))
os.putenv('GST_DEBUG_DUMP_DIR_DIR', '/mnt/ssd/csi_pipeline/gst_debug_info/debug_dump')

app_context = Gst.Structure.new_empty('app_context')

def overlay_parts_fetcher():
    can_client = app_context.get_value('can_client')
    print('[THREAD] Starting overlay_parts_fetcher', flush=True)
    while True:
        time.sleep(0.1)

def buffer_monitor_probe(pad, info, camera_name):
    buffer = info.get_buffer()
    can_client = app_context.get_value('can_client')
    if buffer:
        can_client.update_camera_status(camera=camera_name)
    return Gst.PadProbeReturn.OK

def nozzlenet_src_pad_buffer_probe(pad, info, u_data):
    logger = app_context.get_value('app_context_v2').logger
    can_client = app_context.get_value('can_client')
    state_machine = app_context.get_value('state_machine')
    columns = app_context.get_value('camera_columns')
    prediction_dict = dict.fromkeys(columns, 0.0)
    frame_number = 0
    obj_id = 0
    deleted = 1
    nozzle_status_string = ''
    action_object_string = None
    highest_confidence = 0.0
    nozzle_status_string = None
    action_object_string = None
    timenow = datetime.now()
    search_item_list_ = app_context.get_value('search_item_list')
    overlay_parts = app_context.get_value('overlay_parts')

    gst_buffer = info.get_buffer()

    if not gst_buffer:
        sys.stderr.write('unable to get pgie src pad buffer\n')
        return

    nn_fps_counter_ = app_context.get_value('nn_fps_counter')
    fps_count = nn_fps_counter_.get_fps()

    if fps_count and can_client.connected:
        can_client.update_fps('nn', int(hex(fps_count), 16))
    
    batch_meta = pyds.gst_buffer_get_nvds_batch_meta(hash(gst_buffer))
    display_meta = pyds.nvds_acquire_display_meta_from_pool(batch_meta)
    l_frame = batch_meta.frame_meta_list
    frame_meta = pyds.NvDsFrameMeta.cast(l_frame.data)
    ndetections = frame_meta.num_obj_meta
    l_obj = frame_meta.obj_meta_list
    frame_number = frame_meta.frame_num

    # Inference display setup
    display_meta.num_labels = 2
    py_nvosd_text_params = display_meta.text_params[0]
    py_nvosd_pm_params = display_meta.text_params[1]

    py_nvosd_text_params.display_text = 'Frame Number={} | FPS {} | Num detection =  {} | Max Confidence = {:.2f} | Nozzle status = {} | Action object = {}\n Nozzle CAN = {} | Fan CAN = {} | Time = {} | SM Current Status = {} | SM Current State = {}\n SMS Time Difference = {:.3f} | Action Object Status = {} | Action Object Diffrence = {:.3f}'.format(frame_number, fps_count, ndetections, highest_confidence, nozzle_status_string, action_object_string, overlay_parts.get('sm_nozzle_state', 'N/A'), overlay_parts.get('sm_fan_speed', 'N/A'), timenow, overlay_parts.get('sm_current_status', 'N/A'), overlay_parts.get('sm_current_state', 'N/A'), overlay_parts.get('sm_time_difference', 'N/A'), overlay_parts.get('sm_ao_status', 'N/A'), overlay_parts.get('sm_ao_difference', 'N/A'))
    py_nvosd_text_params.x_offset = 1
    py_nvosd_text_params.y_offset = 1
    py_nvosd_text_params.font_params.font_name = 'Serif'
    py_nvosd_text_params.font_params.font_size = 1
    py_nvosd_text_params.font_params.font_color.set(1.0, 1.0, 1.0, 1.0)
    py_nvosd_text_params.set_bg_clr = 1
    py_nvosd_text_params.text_bg_clr.set(0.0, 0.0, 0.0, 0.5)
    py_nvosd_pm_params.display_text = f"S1_PM10={overlay_parts.get('s1_pm10', 0)} | S2_PM10={overlay_parts.get('s2_pm10', 'N/A')} | S3_PM10={overlay_parts.get('s3_pm10', 'N/A')} | S4_PM10={overlay_parts.get('s4_pm10', 'N/A')} | S5_PM10={overlay_parts.get('s5_pm10', 'N/A')}"
    py_nvosd_pm_params.x_offset = 0
    py_nvosd_pm_params.y_offset = 1040
    py_nvosd_pm_params.font_params.font_name = 'Serif'
    py_nvosd_pm_params.font_params.font_size = 1
    py_nvosd_pm_params.font_params.font_color.set(1.0, 1.0, 1.0, 1.0)
    py_nvosd_pm_params.set_bg_clr = 1
    py_nvosd_pm_params.text_bg_clr.set(0.0, 0.0, 0.0, 0.5)

    while l_obj is not None:
        try:
            obj_meta = pyds.NvDsObjectMeta.cast(l_obj.data)
        except StopIteration:
            pass
        try:
            l_obj = l_obj.next
        except StopIteration:
            pass
        if obj_meta.class_id not in search_item_list_:
            print('class id = ', obj_meta.class_id)
            print('search item list = ', search_item_list_)
            pyds.nvds_remove_obj_meta_from_frame(frame_meta, obj_meta)
            print(f'class = {obj_meta.class_id} object deleted , total deleted = {deleted}')
            deleted += 1
            obj_id += 1
        else:
            if obj_meta.class_id == DETECTION_CATEGORIES.PGIE_CLASS_ID_NOZZLE_CLEAR.value:
                nozzle_status_string = 'clear'
                obj_meta.rect_params.border_color.set(0.1411, 0.8019, 0.3254, 0.9)
                prediction_dict['nozzle_clear'] = 1.0
            elif obj_meta.class_id == DETECTION_CATEGORIES.PGIE_CLASS_ID_NOZZLE_BLOCKED.value:
                nozzle_status_string = 'blocked'
                obj_meta.rect_params.border_color.set(1.0, 0.3764, 0.2156, 0.9)
                prediction_dict['nozzle_blocked'] = 1.0
            elif obj_meta.class_id == DETECTION_CATEGORIES.PGIE_CLASS_ID_CHECK_NOZZLE.value:
                nozzle_status_string = 'check'
                obj_meta.rect_params.border_color.set(0.96078431, 0.57647059, 0.19215686, 0.9)
                prediction_dict['check_nozzle'] = 1.0
            elif obj_meta.class_id == DETECTION_CATEGORIES.PGIE_CLASS_ID_GRAVEL.value:
                nozzle_status_string = 'gravel'
                obj_meta.rect_params.border_color.set(0.678, 0.847, 0.902, 0.9)
                prediction_dict['gravel'] = 1.0
            elif obj_meta.class_id == DETECTION_CATEGORIES.PGIE_CLASS_ID_ACTION_OBJECT.value:
                action_object_string = 'true'
                obj_meta.rect_params.border_color.set(1.0, 0.0, 0.48627451, 0.9)
                prediction_dict['action_object'] = 1.0
            obj_meta.rect_params.border_width = 5
            if obj_meta.confidence > highest_confidence:
                highest_confidence = obj_meta.confidence
                prediction_dict['confidence'] = highest_confidence
    try:
        state_machine.status_send(recieved_ns=nozzle_status_string, recieved_aos=action_object_string)
    except Exception as e:
        print(f'State machine status send error: {e}')
    prediction_dict['sm_current_state'] = state_machine.get_current_state()

    if can_client.connected:
        try:
            can_client.update_can_bytes({'fan_byte': {'operation': 'update_bits', 'value': int(hex(state_machine.fan_speed), 16), 'mask': 15}})
        except Exception as e:
            print(f'CAN communication error: {e}')
        try:
            can_client.update_can_bytes({'nozzle_byte': {'operation': 'update_bits', 'value': int(hex(state_machine.nozzle_state), 16), 'mask': 15}})
        except Exception as e:
            print(f'CAN communication error: {e}')
    
    pyds.nvds_add_display_meta_to_frame(frame_meta, display_meta)
    prediction_dict['time'] = f"{datetime.now().strftime('%H:%M:%S.%f')[:-5]}00"

    for key, value in prediction_dict.items():
        if can_client and can_client.connected:
            try:
                can_client.send_data(key=key, value=value)
            except Exception as e:
                logger.debug(f'CAN communication error: {e}')
    return Gst.PadProbeReturn.OK

def load_latest_init_status(base_filename, app_context=app_context):
    """
    Load the latest initial status from a file matching a specified pattern in /tmp directory.

    Parameters:
    - base_filename: The base filename pattern to search for, without the timestamp and extension.

    Returns:
    - The content of the latest file as a Python dictionary.

    Raises:
    - FileNotFoundError: If no file matching the pattern is found.
    """
    logger = app_context.get_value('app_context_v2').logger
    pattern = f'/tmp/{base_filename}_*.json'
    logger.debug(f'Searching for files matching pattern {pattern}')
    files = glob.glob(pattern)
    if not files:
        logger.error(f'No files found for pattern {base_filename}. This is a fatal error.')
        return -1

    def extract_datetime(filename):
        timestamp_str = filename.split('_')[-1].rstrip('.json')
        return datetime.strptime(timestamp_str, '%Y%m%d%H%M')
    
    latest_file = max(files, key=lambda x: extract_datetime(x))
    logger.debug(f'Latest file found: {latest_file}')
    with open(latest_file, 'r') as f:
        content = json.load(f)
        app_context.set_value('init_config', content)
        return 0

def notify_systemd(msg, app_context=app_context):
    """
    notifies systemd with the messages but ensure duplicate notifications are not made 
    """
    context = app_context
    logger = context.get_value('app_context_v2').logger
    mode = context.get_value('SSWP_RUN_MODE')
    if mode != 'SYSTEMD_NOTIFY_SERVICE':
        logger.debug(f'mode is not SYSTEMD_NOTIFY_SERVICE, skipping notification to systemd: {msg}')
        return
    last_notification = context.get_value('last_notificationsent_to_systemd')
    if last_notification != msg:
        logger.debug(f'Sending notification to systemd: {msg}')
        systemd_notifier(msg)
        app_context.set_value('last_notificationsent_to_systemd', msg)
    else:
        logger.debug(f'Duplicate notification to systemd: {msg}, skipping...')

def systemd_notifier(msg='READY=1', app_context=app_context):
    """
    Notifies the systemd service manager that the service is ready.
    This function is intended for use with services of type notify.
    if sending from a different process the message must have the format (e.g. "READY=1 MAINPID=1234", but this is not tested yet)
    """
    logger = app_context.get_value('app_context_v2').logger
    if 'NOTIFY_SOCKET' in os.environ:
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sock:
                address = os.environ['NOTIFY_SOCKET']
                if address[0] == '@':
                    address = '\x00' + address[1:]
                sock.sendto(msg.encode('utf-8'), address)
        except Exception as e:
            pass
            logger.error(f'Error notifying systemd: {e}')
    if False:
        pass
    logger.debug('Not running under systemd management.')

def unix_socket_server(socket_path, stop_event, app_context=app_context):
    """
    unix socket server function to communicate with other elements
    
    """
    logger = app_context.get_value('app_context_v2').logger
    pipeline = app_context.get_value('pipeline')
    loop = app_context.get_value('main_loop')
    try:
        os.unlink(socket_path)
    except OSError:
        if os.path.exists(socket_path):
            raise
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.bind(socket_path)
    sock.listen(1)
    logger.debug(f'listening on {socket_path} to receive commands from the main controller')
    while not stop_event.is_set():
        sock.settimeout(1.0)
        try:
            connection, client_address = sock.accept()
        except socket.timeout:
            continue
        except Exception as e:
            pass
            logger.error(f'Error accepting connection: {e}')
        try:
            while True:
                data = connection.recv(1024)
                if data:
                    logger.debug(f'received {data} from the main controller')
                    command = data.decode('utf-8').strip()
                    logger.debug(f'recived command: {command}')
                    if command == 'stop':
                        logger.debug('stop command received, setting stop event ***************')
                        write_dotfile(pipeline)
                        stop_event.set()
                        stop_secs = 3
                        GLib.timeout_add_seconds(1, stop, loop, pipeline, stop_secs, app_context)
                    else:
                        break
                else:
                    break
        finally:
            connection.close()
    print('closing the socket')
    sock.close()

def write_dotfile(pipeline, app_context=app_context):
    """
    Write a dot file for the pipeline
    """
    logger = app_context.get_value('app_context_v2').logger
    full_path_and_filename = app_context.get_value('full_path_and_filename')
    filename = os.path.basename(full_path_and_filename).split('.')[0]
    logger.debug(f'Creating dot file for {filename} pipeline')
    timestamp = datetime.now().strftime('%Y_%m_%d_%H_%M_%S')
    logger.debug(f"dot file path relative to this script dir -> {os.environ.get('GST_DEBUG_DUMP_DOT_DIR')}/python_ROI_{timestamp}.dot")
    if os.path.isfile(f"{os.environ.get('GST_DEBUG_DUMP_DOT_DIR')}/python_ROI_{timestamp}.dot"):
        logger.debug(f"dot file already exists at {os.environ.get('GST_DEBUG_DUMP_DOT_DIR')}/python_ROI_{timestamp}.dot")
        return
    Gst.debug_bin_to_dot_file(pipeline, Gst.DebugGraphDetails.ALL, f'python_ROI_{timestamp}')
    logger.debug("******making a symlink to the latest dot file at {os.environ.get('GST_DEBUG_DUMP_DOT_DIR')}/python_ROI_latest.dot ")
    os.system(f"/usr/bin/ln -sf {os.environ.get('GST_DEBUG_DUMP_DOT_DIR')}/python_ROI_{timestamp}.dot {os.environ.get('GST_DEBUG_DUMP_DOT_DIR')}/python_ROI_latest.dot")
    dotfilename = f"{os.environ.get('GST_DEBUG_DUMP_DOT_DIR')}/python_{timestamp}.dot"
    if os.path.isfile(dotfilename):
        logger.debug(f'dot file created: {dotfilename}')
    else:
        logger.debug(f'dot file not created at {dotfilename}, present working directory: {os.getcwd()}')

def stop(loop, pipeline, stop_secs_=5, app_context=app_context):
    _, position = pipeline.query_position(Gst.Format.TIME)
    stop_secs = stop_secs_
    pass
    logger = app_context.get_value('app_context_v2').logger
    if position > stop_secs * Gst.SECOND:
        logger.debug('************** Stopping the pipeline on request..! ***************************')
        full_path_and_filename = app_context.get_value('full_path_and_filename')
        filename = os.path.basename(full_path_and_filename).split('.')[0]
        logger.debug(f'Creating dot file for {filename} pipeline')
        timestamp = datetime.now().strftime('%Y_%m_%d_%H_%M_%S')
        logger.debug(f"dot file path relative to this script dir -> {os.environ.get('GST_DEBUG_DUMP_DOT_DIR')}/python_ROI_{timestamp}.dot")
        Gst.debug_bin_to_dot_file(pipeline, Gst.DebugGraphDetails.ALL, f'python_ROI_{timestamp}')
        logger.debug("******making a symlink to the latest dot file at {os.environ.get('GST_DEBUG_DUMP_DOT_DIR')}/python_ROI_latest.dot ")
        os.system(f"/usr/bin/ln -sf {os.environ.get('GST_DEBUG_DUMP_DOT_DIR')}/python_ROI_{timestamp}.dot {os.environ.get('GST_DEBUG_DUMP_DOT_DIR')}/python_ROI_latest.dot")
        dotfilename = f"{os.environ.get('GST_DEBUG_DUMP_DOT_DIR')}/python_{timestamp}.dot"
        if os.path.isfile(dotfilename):
            logger.debug(f'dot file created: {dotfilename}')
        else:
            logger.debug(f'dot file not created at {dotfilename}, present working directory: {os.getcwd()}')
        app_context.set_value('shutdown_initiated_by_user_process', True)
        pipeline.send_event(Gst.Event.new_eos())
        logger.debug(f'Stopping after {stop_secs} seconds')
        return False
    return True

def create_replacement_camera_bin(camera_name, app_context):
    """Create a replacement camera bin with videotestsrc that syncs with pipeline time"""
    logger = app_context.get_value('app_context_v2').logger
    pipeline = app_context.get_value('pipeline')
    replacement_bin = Gst.Bin.new(f'fake_{camera_name}_camera_bin')
    replacement_bin.set_property('message-forward', True)
    fake_source = make_element('videotestsrc', f'fake_videotestsrc_{camera_name}')
    fake_source.set_property('pattern', 2)
    fake_source.set_property('is-live', True)
    pipeline_time = pipeline.get_clock().get_time()
    pipeline_base_time = pipeline.get_base_time()
    logger.debug(f'Pipeline time: {pipeline_time}, base time: {pipeline_base_time}')
    capsfilter = make_element('capsfilter', f'fake_capsfilter_{camera_name}')
    caps = Gst.Caps.from_string('video/x-raw, format=I420, width=1920, height=1080, framerate=30/1')
    capsfilter.set_property('caps', caps)
    clocksync = make_element('clocksync', f'fake_clocksync_{camera_name}')
    clocksync.set_property('sync', True)
    clocksync.set_property('ts-offset', 0)
    queue = make_element('queue', f'fake_queue_{camera_name}')
    queue.set_property('flush-on-eos', True)
    queue.set_property('max-size-buffers', 2)
    queue.set_property('leaky', 2)
    converter = make_element('nvvideoconvert', f'fake_nvvidconv_{camera_name}')
    elements = [fake_source, capsfilter, clocksync, queue, converter]
    for element in elements:
        if not element:
            logger.error(f'Failed to create replacement element for {camera_name}')
            return
        replacement_bin.add(element)
    else:
        if not fake_source.link(capsfilter) or not capsfilter.link(clocksync) or (not clocksync.link(queue)) or (not queue.link(converter)):
            logger.error(f'Failed to link replacement elements for {camera_name}')
            return
        replacement_bin.add_pad(Gst.GhostPad.new('src', get_static_pad(converter, 'src')))
        logger.debug(f'Created replacement camera bin with timestamp sync for {camera_name}')
        return replacement_bin

def replace_camera_src(message, loop, app_context=app_context):
    print('replacing camera')
    logger = app_context.get_value('app_context_v2').logger
    pipeline = app_context.get_value('pipeline')
    cameras = app_context.get_value('init_config')['cameras']
    container = pipeline.get_by_name('multi_nvargus_bin')
    streammux = pipeline.get_by_name('multi_nvargus_streammux')
    probe_ids = app_context.get_value('probe_ids')
    if not app_context.has_field('replacement_pads'):
        app_context.set_value('replacement_pads', [])
    source_name = message.src.get_name()
    camera_name = source_name.replace('_camera_source', '')
    logger.debug(f'Attempting to replace camera source: {camera_name}')
    for i, camera in enumerate(cameras):
        if camera['name'] == camera_name:
            if camera['name'] == 'primary_nozzle':
                print('Critical Error, Primary Camera Failure')
                exit(1)
                return
            print(f"Replacing camera source for {camera['name']}")
            try:
                device_path = camera['device_path']
                camera_id = int(device_path.split('/dev/video')[-1])
                source_bin = container.get_by_name(f'{camera_name}_camera_bin')
                if not source_bin:
                    logger.error(f'Could not find camera bin for {camera_name}')
                    return
                source_camera = source_bin.get_by_name(f'{camera_name}_camera_source')
                if not source_camera:
                    logger.error(f'Could not find camera source for {camera_name}')
                    return
                pipeline.set_state(Gst.State.PAUSED)
                id = probe_ids[camera_name]['buffer_monitor']
                source_camera_src_pad = source_camera.get_static_pad('src')
                if source_camera_src_pad:
                    source_camera_src_pad.send_event(Gst.Event.new_flush_start())
                    source_camera_src_pad.send_event(Gst.Event.new_flush_stop(False))
                source_camera_src_pad.remove_probe(id)
                probe_ids[camera_name]['buffer_monitor'] = None
                if camera_name in ('front', 'rear') and probe_ids[camera_name]['csi_probe'] is not None:
                    logger.debug(f'Removing CSI probe for {camera_name}')
                    csi_probe_queue = pipeline.get_by_name(f'queue_{camera_name}_csiprobe')
                    if csi_probe_queue:
                        csi_probe_queue_src_pad = csi_probe_queue.get_static_pad('src')
                        if csi_probe_queue_src_pad:
                            csi_probe_id = probe_ids[camera_name]['csi_probe']
                            if csi_probe_id:
                                csi_probe_queue_src_pad.remove_probe(csi_probe_id)
                                probe_ids[camera_name]['csi_probe'] = None
                logger.debug('Setting source bin to NULL')
                source_camera.set_state(Gst.State.PAUSED)
                pad_name = f'sink_{camera_id}'
                print('releasing pad:', pad_name)
                sinkpad = streammux.get_static_pad(pad_name)
                if sinkpad:
                    sinkpad.send_event(Gst.Event.new_flush_stop(False))
                    streammux.release_request_pad(sinkpad)
                replacement_bin = create_replacement_camera_bin(camera_name, app_context)
                if not replacement_bin:
                    logger.error(f'Failed to create replacement bin for {camera_name}')
                    return
                container.add(replacement_bin)
                link_static_srcpad_pad_to_request_sinkpad(replacement_bin, streammux, sink_pad_index=camera_id)
                replacement_bin.set_state(Gst.State.PLAYING)
                pipeline.set_state(Gst.State.PLAYING)
                logger.debug(f'Successfully created and linked replacement bin for {camera_name}')
                Gst.debug_bin_to_dot_file(pipeline, Gst.DebugGraphDetails.ALL, 'python_replaced')
                print(f'Replaced camera source for {camera_name} with fake source')
                return
            except Exception as e:
                logger.error(f'Error during camera replacement: {e}')
                return

def bus_call(bus, message, loop):
    t = message.type
    if t == Gst.MessageType.EOS:
        sys.stdout.write('EOS recived on the bus checking...\n')
        eos_source = message.src.get_name()
        sys.stdout.write(f'End of stream came from {eos_source}\n')
        pass
        shutdown_initiated_by_user_process = app_context.get_value('shutdown_initiated_by_user_process')
        if shutdown_initiated_by_user_process:
            sys.stdout.write('Shutdown was initiated by the user process\n')
            print('getting pipeline from app context')
            pipeline = app_context.get_value('pipeline')
            if pipeline:
                state = pipeline.get_state(Gst.CLOCK_TIME_NONE)
                sys.stdout.write(f'pipeline current state: {state}\n')
                sys.stdout.write('setting pipeline to NULL state\n')
                ret = pipeline.set_state(Gst.State.NULL)
                if ret == Gst.StateChangeReturn.FAILURE:
                    sys.stderr.write('Failed to set pipeline to NULL state\n')
                loop.quit()
    elif t == Gst.MessageType.WARNING:
        err, debug = message.parse_warning()
        sys.stderr.write('Warning: %s: %s\n' % (err, debug))
    elif t == Gst.MessageType.ERROR:
        err, debug = message.parse_error()
        sys.stderr.write('Error: %s: %s \n' % (err, debug))
        print(err)
        if 'NvArgusCameraSrc: TIMEOUT' in str(err):
            print('nvarguscamerasrc: Timeout error detected, creating fake bin')
            replace_camera_src(message, loop, app_context)
            return False
        notify_systemd('STOPPING=1')
        loop.quit()
        return True

def gst_debug_log(message, level=Gst.DebugCategory, obj=None):
    """
    Note: this is not yet finished being implemented

    simplified Gst.debug_log wrapper, with automatic extraction of the filename, function name and line number
    :param message: the message to log
    :param level: the log level
    :param obj: the object to log
    """
    frame = inspect.currentframe().f_back
    originator = frame.f_globals.get('__name__', '__main__')
    print(f'frame: {frame}')
    filename = frame.f_code.co_filename
    function_name = frame.f_code.co_name
    line_number = frame.f_lineno
    category = Gst.DebugCategory.get_default()
    category.log(category, level, f'{filename}:{function_name}:{line_number}', obj, message)
    print(f'GST_DEBUG: {message}')

def make_element(element_name, specific_name=None):
    """
    Creates a Gstreamer element with unique name
    Unique name is created by adding element type and index e.g. `element_name-i`
    Unique name is essential for all the element in pipeline otherwise gstreamer will throw exception.
    :param element_name: The name of the element to create
    :param i: the index of the element in the pipeline
    :return: A Gst.Element object
    """
    element = Gst.ElementFactory.make(element_name, element_name)
    if not element:
        sys.stderr.write(' Unable to create {0}'.format(element_name))
        return
    if specific_name:
        if isinstance(specific_name, str):
            element.set_property('name', '{0}'.format(specific_name))
            return element
        if isinstance(specific_name, int):
            element.set_property('name', '{0}_{1}'.format(element_name, specific_name))
            return element
        sys.stderr.write('specific_name should be a string or an integer')
        return
    return element

def demuxer_pad_added(context, pad, target_sinkpad):
    print('demuxer pad added')
    string = pad.query_caps(None).to_string()
    if string.startswith('video/x-h265'):
        print('linking demuxer src pad to source queue sink pad (h265)')
        pad.link(target_sinkpad)
    elif string.startswith('video/x-h264'):
        print('linking demuxer src pad to source queue sink pad (h264)')
        pad.link(target_sinkpad)
    else:
        print(f'error: video/x-h264 stream not found, string: {string}')

def make_bucher_ds_filesrc(file_path, codec, app_context=app_context):
    """
    Create a filesrc element for the bucher deepstream pipeline
    """
    logger = app_context.get_value('app_context_v2').logger
    bucher_ds_filesrc_bin = Gst.Bin.new('bucher_ds_filesrc_bin')
    if not bucher_ds_filesrc_bin:
        logger.error('Failed to create bucher_ds_filesrc_bin')
        return
    bucher_ds_filesrc_bin.set_property('message-forward', True)
    file_name = os.path.basename(file_path)
    filesrc_name = file_name.replace('.', '_')
    bucher_ds_filesrc_bin.set_property('name', f'bucher_ds_filesrc_bin_{filesrc_name}')
    logger.debug(f'creating bucher_ds_filesrc_bin for file: {file_path}')
    filesrc = make_element('filesrc', f'filesrc_{filesrc_name}')
    if filesrc:
        filesrc.set_property('location', str(file_path))
    Gst.Bin.add(bucher_ds_filesrc_bin, filesrc)
    demuxer = make_element('qtdemux', f'qtdemux_{filesrc_name}')
    Gst.Bin.add(bucher_ds_filesrc_bin, demuxer)
    filesrc.link(demuxer)
    source_queue = make_element('queue', f'source_queue_{filesrc_name}')
    Gst.Bin.add(bucher_ds_filesrc_bin, source_queue)
    source_queue_sinkpad = get_static_pad(source_queue, 'sink')
    demuxer.connect('pad-added', lambda context, pad: demuxer_pad_added(context, pad, source_queue_sinkpad))
    if codec == 'h264':
        parser = make_element('h264parse', f'h264parse_{filesrc_name}')
    elif codec == 'h265':
        parser = make_element('h265parse', f'h265parse_{filesrc_name}')
    else:
        logger.error(f'Unsupported file extension: {codec}')
        return
    Gst.Bin.add(bucher_ds_filesrc_bin, parser)
    source_queue.link(parser)
    decoder = make_element('nvv4l2decoder', f'nvv4l2decoder_{filesrc_name}')
    Gst.Bin.add(bucher_ds_filesrc_bin, decoder)
    parser.link(decoder)
    converter_rotate = make_element('nvvideoconvert', f'videoconvert_{filesrc_name}_1')
    Gst.Bin.add(bucher_ds_filesrc_bin, converter_rotate)
    decoder.link(converter_rotate)
    sink_queue = make_element('queue', f'sink_queue_{filesrc_name}')
    Gst.Bin.add(bucher_ds_filesrc_bin, sink_queue)
    converter_rotate.link(sink_queue)
    binsinkpad_ = bucher_ds_filesrc_bin.add_pad(Gst.GhostPad.new('src', sink_queue.get_static_pad('src')))
    if not binsinkpad_:
        logger.error('Failed to add ghost src pad to bucher_ds_filesrc_bin')
        return
    return bucher_ds_filesrc_bin

def make_argus_camera_source(sensor_id, camera_config=None, app_context=app_context):
    """
    Create a argus camera source element, takes the sensor id and camera configuration as input
    the camera configuration is a dictionary with the following keys
    - sensor-mode : the sensor mode to use: default is "3"
    - gainrange : the gain range to use: default is "1.0 8.0"
    - exposuretimerange : the exposure time range to use: default is "20000 336980000"
    - ispdigitalgainrange : the isp digital gain range to use: default is "1 256"
    :param sensor_id: the sensor id to use
    :param camera_config: the camera configuration (optional)

    camera config structure example

    camera_config = {
        "gainrange": "1.0 8.0",
        "exposuretimerange": "20000 336980000",
        "ispdigitalgainrange": "1 256",
        "sensor-mode": 3
    }
    """
    logger = app_context.get_value('app_context_v2').logger
    camera_config = camera_config or {}
    source = make_element('nvarguscamerasrc', sensor_id)
    if source:
        logger.debug(f'setting nvarguscamerasrc parameters for sensor id: {sensor_id}')
        source.set_property('sensor-id', int(sensor_id))
        source.set_property('sensor-mode', camera_config.get('sensor-mode', 3))
        source.set_property('gainrange', camera_config.get('gainrange', '1.0 8.0'))
        source.set_property('exposuretimerange', camera_config.get('exposuretimerange', '20000 336980000'))
        source.set_property('ispdigitalgainrange', camera_config.get('ispdigitalgainrange', '1 256'))
        return source
    sys.stderr.write('unable to create argus camera source')
    return

def get_request_pad(element, pad_name):
    """
    Get a request pad from the element
    :param element: the element to get the request pad from
    :param pad_name: the name of the pad to get
    :return: the request pad
    """
    pad = element.get_request_pad(pad_name)
    if not pad:
        sys.stderr.write('Unable to get the {0} pad of {1}\n'.format(pad_name, element.get_name()))
    return pad

def get_static_pad(element, pad_name):
    """
    Get a static pad from the element
    :param element: the element to get the static pad from
    :param pad_name: the name of the pad to get
    :return: the static pad
    """
    pad = element.get_static_pad(pad_name)
    if not pad:
        sys.stderr.write('Unable to get the {0} pad of {1}\n'.format(pad_name, element.get_name()))
    return pad

def link_static_srcpad_pad_to_request_sinkpad(src, sink, sink_pad_index=None):
    """
    brief: get a static pad from the source element, get a request pad from the sink element and link them together,
         if the pad names are not explicitly specidied, the function will use the default pad names
    Link the source element to the sink element using the source pad name and sink pad name
    :param src: the source element
    :param src_pad_name: the name of the source pad (static pad)
    :param sink: the sink element
    :param sink_pad_name: the name of the sink pad (request pad)
    """
    request_pad_index = 0
    src_pad_name = 'src'
    if sink_pad_index is None:
        sink_pad_index = 'sink_%d' % request_pad_index
    if isinstance(sink_pad_index, int):
        sink_pad_index = 'sink_%d' % sink_pad_index
    else:
        sys.stderr.write('warning: sink pad name is not an integer, using default pad name\n')
        sink_pad_index = 'sink_%d' % request_pad_index
    src_pad = get_static_pad(src, src_pad_name)
    sink_pad = get_request_pad(sink, sink_pad_index)
    if src_pad and sink_pad:
        src_pad.link(sink_pad)
    else:
        sys.stderr.write(f'error: pad link error, src: {src.get_name()} pad: {src_pad_name}, sink: {sink.get_name()} pad: {sink_pad_index}\n')

def link_request_srcpad_to_static_sinkpad(src, sink, src_pad_index=None, sink_pad_index=None):
    """
    brief: get a request pad from the source element, get a static pad from the sink element and link them together,
         if the pad names are not explicitly specified, the function will use the default pad names
    Link the source element to the sink element using the source pad name and sink pad name
    :param src: the source element
    :param src_pad_name: the name of the source pad (request pad)
    :param sink: the sink element
    :param sink_pad_name: the name of the sink pad (static pad)
    """
    request_pad_index = 0
    if src_pad_index is None:
        src_pad_index = 'src_%u'
    if sink_pad_index is None:
        sink_pad_index = 'sink'
    if isinstance(src_pad_index, int) and src_pad_index is not None:
        src_pad_index = 'src_%u' % src_pad_index
    if isinstance(sink_pad_index, int) and sink_pad_index is not None:
        sink_pad_index = 'sink_%u' % sink_pad_index
    try:
        src_pad = get_request_pad(src, src_pad_index)
        sink_pad = get_static_pad(sink, sink_pad_index)
        if src_pad and sink_pad:
            src_pad.link(sink_pad)
        else:
            sys.stderr.write(f'error: pad link error, src: {src.get_name()} pad: {src_pad_index}, sink: {sink.get_name()} pad: {sink_pad_index}\n')
    except Exception as e:
        sys.stderr.write(f'error: {e}\n')
        sys.stderr.write(f'error: pad link error, src: {src.get_name()} pad: {src_pad_index}, sink: {sink.get_name()} pad: {sink_pad_index}\n')
        raise e

def on_message(bus, message, loop, pipeline):
    """
    Callback for GStreamer Bus messages
    """
    mtype = message.type
    if mtype == Gst.MessageType.EOS:
        print('End-Of-Stream reached. Attempting to reconnect...')
        pipeline.set_state(Gst.State.NULL)
        naptime.sleep(1)
        pipeline.set_state(Gst.State.PLAYING)
    elif mtype == Gst.MessageType.ERROR:
        err, debug = message.parse_error()
        print(f'Error: {err}, {debug}')
        loop.quit()

def create_csiprobebin(app_context, flip_method) -> Gst.Bin:
    """
    Create a CSI probe bin, this will have the form: 
    nvvidconv -> capsfilter -> queue -> nvvidconv -> capsfilter -> queue -> videorate -> queue

    """
    logger = app_context.get_value('app_context_v2').logger
    
    csi_probe_bin = Gst.Bin.new('csi_probe_bin')    
    csi_probe_bin.set_property('message-forward', True)
    nvstreammux_road_pgie = Gst.ElementFactory.make('nvstreammux', 'nvstreammux_road_pgie')
    nvstreammux_garbage_pgie = Gst.ElementFactory.make('nvstreammux', 'nvstreammux_garbage_pgie')
    queue_pre_road_pgie = Gst.ElementFactory.make('queue', 'queue_pre_road_pgie')
    queue_pre_garbage_pgie = Gst.ElementFactory.make('queue', 'queue_pre_garbage_pgie')
    road_nvinfer_engine = Gst.ElementFactory.make('nvinfer', 'road_nvinfer_engine')
    garbage_nvinfer_engine = Gst.ElementFactory.make('nvinfer', 'garbage_nvinfer_engine')
    queue_post_garbage_pgie = Gst.ElementFactory.make('queue', 'queue_post_garbage_pgie')
    segvisual = Gst.ElementFactory.make('nvsegvisual', 'segvisual')
    videorate_out_csi = Gst.ElementFactory.make('videorate', 'videorate_out_csi')

    videorate_out_csi.set_property("skip-to-first", True)
    segvisual.set_property('alpha', 0)
    segvisual.set_property('original-background', True)
    segvisual.set_property('width', 608)
    segvisual.set_property('height', 416)
    nvstreammux_garbage_pgie.set_property('width', 1920)
    nvstreammux_garbage_pgie.set_property('height', 1080)
    nvstreammux_garbage_pgie.set_property('batch-size', 2)
    nvstreammux_road_pgie.set_property('width', 1920)
    nvstreammux_road_pgie.set_property('height', 1080)
    nvstreammux_road_pgie.set_property('batch-size', 2)
    road_nvinfer_engine.set_property('config-file-path', '/mnt/ssd/csi_pipeline/config/road_pgie_config.txt')
    garbage_nvinfer_engine.set_property('config-file-path', '/mnt/ssd/csi_pipeline/config/garbage_pgie_config.txt')
    queue_pre_road_pgie.set_property('leaky', 2)
    queue_pre_garbage_pgie.set_property('leaky', 2)
    queue_post_garbage_pgie.set_property('leaky', 2)
    queue_pre_road_pgie.set_property('max-size-buffers', 1)
    queue_pre_garbage_pgie.set_property('max-size-buffers', 1)
    queue_post_garbage_pgie.set_property('max-size-buffers', 1)
    queue_pre_road_pgie.set_property('flush-on-eos', True)
    queue_pre_garbage_pgie.set_property('flush-on-eos', True)
    queue_post_garbage_pgie.set_property('flush-on-eos', True)
    rgba_to_nv12_convert = Gst.ElementFactory.make('nvvideoconvert', 'rgba_to_nv12_convert')
    rgba_to_nv12_capsfilter = Gst.ElementFactory.make('capsfilter', 'rgba_to_nv12_capsfilter')
    rgba_to_nv12_capsfilter.set_property("caps", Gst.Caps.from_string("video/x-raw(memory:NVMM), format=(string)NV12, width=960, height=540"))
    output_queue = Gst.ElementFactory.make('queue', 'output_queue')
    output_queue.set_property('leaky', 2)
    output_queue.set_property('max-size-buffers', 2)
    output_queue.set_property('flush-on-eos', True)
    output_queue.set_property('max-size-time', 66000000)
    
    Gst.Bin.add(csi_probe_bin, segvisual)
    Gst.Bin.add(csi_probe_bin, queue_pre_road_pgie)
    Gst.Bin.add(csi_probe_bin, queue_pre_garbage_pgie)
    Gst.Bin.add(csi_probe_bin, road_nvinfer_engine)
    Gst.Bin.add(csi_probe_bin, garbage_nvinfer_engine)
    Gst.Bin.add(csi_probe_bin, queue_post_garbage_pgie)
    Gst.Bin.add(csi_probe_bin, rgba_to_nv12_convert)
    Gst.Bin.add(csi_probe_bin, rgba_to_nv12_capsfilter)
    Gst.Bin.add(csi_probe_bin, output_queue)
    #Gst.Bin.add(csi_probe_bin, videorate_out_csi)

    csi_probe_bin.add_pad(Gst.GhostPad.new('sink', get_static_pad(queue_pre_road_pgie, 'sink')))
    queue_pre_road_pgie.link(road_nvinfer_engine)
    road_nvinfer_engine.link(queue_pre_garbage_pgie)
    queue_pre_garbage_pgie.link(garbage_nvinfer_engine)
    garbage_nvinfer_engine.link(segvisual)
    segvisual.link(queue_post_garbage_pgie)
    queue_post_garbage_pgie.link(rgba_to_nv12_convert)
    rgba_to_nv12_convert.link(rgba_to_nv12_capsfilter)
    #rgba_to_nv12_capsfilter.link(videorate_out_csi)
    #videorate_out_csi.link(output_queue)
    rgba_to_nv12_capsfilter.link(output_queue)
    queue_post_garbage_pgie_probe = get_static_pad(queue_post_garbage_pgie, 'src')
    queue_post_garbage_pgie_probe.add_probe(Gst.PadProbeType.BUFFER, compute_csi_buffer_probe, 0)
    csi_probe_bin.add_pad(Gst.GhostPad.new('src_0', get_static_pad(output_queue, 'src')))
    return csi_probe_bin

def create_udpsinkbin(app_context):
    """
    Create a udp sinkbin, this will have the form:
    queue -> nvvideoconvert -> capsfilter -> encoder -> identity -> codecparse -> rtppay -> udpsink
    """
    logger = app_context.get_value("app_context_v2").logger
    serial_number = app_context.get_value('serial_number')
    file_start_time = app_context.get_value('file_start_time')
    log_duration = app_context.get_value('log_duration')
    codec = 'h265'
    logfile = f"/mnt/syslogic_sd_card/{serial_number}_{file_start_time}_inference"

    # Create a bin to hold the elements
    udpsinkbin = Gst.Bin.new("udpsinkbin")
    if not udpsinkbin:
        logger.error("Failed to create udpsinkbin")
        return None
    
    udpsinkbin.set_property("message-forward", False) # forward messages to the parent bin

    # Create the elements
    queue = make_element("queue", "udpsink_queue")
    nvvideoconvert = make_element("nvvideoconvert", "udpsink_videoconvert")
    capsfilter = make_element("capsfilter", "udpsink_capsfilter")
    encoder = make_element("nvv4l2h265enc", "udpsink_encoder")
    udpsink_tee = make_element("tee", "udpsink_tee")
    udp_filesink_queue = make_element("queue", "udp_filesink_queue")
    filesink_parser = make_element("h265parse", "filesink_parser")
    udp_filesink = make_element("splitmuxsink", "udp_filesink")
    identity = make_element("identity", "identity0")
    codecparse = make_element("h265parse", "udpsink_codecparse")
    rtppay = make_element("rtph265pay", "udpsink_rtppay")
    udpsink_queue = make_element("queue", "udpsink_queue_before_sink")
    udpsink = make_element("udpsink", "udpsink_udpsink")

    elements = [queue, nvvideoconvert, capsfilter, encoder, udpsink_tee, udp_filesink_queue, filesink_parser, udp_filesink, identity, codecparse, rtppay, udpsink_queue, udpsink]
    for element in elements:
        if not element:
            logger.error(f"Failed to create element: {element}")
            return None

    capsfilter.set_property("caps", Gst.Caps.from_string("video/x-raw(memory:NVMM), format=(string)I420"))
    rtppay.set_property('config-interval', 1)
    udpsink.set_property('host', '172.16.1.35')
    udpsink.set_property('port', 6003)
    udpsink.set_property('sync', False)
    udpsink.set_property('async', False)
    encoder.set_property('bitrate', 6000000)
    encoder.set_property('insert-sps-pps', 1)
    encoder.set_property('qos', True)
    encoder.set_property('profile', 1)
    encoder.set_property('iframeinterval', 3)
    queue.set_property("leaky", "downstream")
    queue.set_property("flush-on-eos", True) 
    queue.set_property("max-size-buffers", 1)
    udpsink_queue.set_property("leaky", "downstream")
    udpsink_queue.set_property("flush-on-eos", True)
    udpsink_queue.set_property("max-size-buffers", 30)
    udp_filesink_queue.set_property("leaky", "downstream") 
    udp_filesink_queue.set_property("flush-on-eos", True)
    udp_filesink_queue.set_property("max-size-buffers", 30)
    udp_filesink.set_property("max-size-time", int(f'{log_duration}000000000')) # 20 minutes
    udp_filesink.set_property('async-handling', True)  
    udp_filesink.set_property('location', f'{logfile}_%d.{codec}')

    for element in elements:
        udpsinkbin.add(element)

    if not queue.link(nvvideoconvert) or \
       not nvvideoconvert.link(capsfilter) or \
       not capsfilter.link(encoder) or \
       not encoder.link(udpsink_tee) or \
       not udp_filesink_queue.link(filesink_parser) or \
       not filesink_parser.link(udp_filesink) or \
       not identity.link(codecparse) or \
       not codecparse.link(rtppay) or \
       not rtppay.link(udpsink_queue) or \
       not udpsink_queue.link(udpsink):
        
        logger.error("Elements could not be linked.")
        return None

    link_request_srcpad_to_static_sinkpad(udpsink_tee, udp_filesink_queue, src_pad_index=0)
    link_request_srcpad_to_static_sinkpad(udpsink_tee, identity, src_pad_index=1)

    sink_pad = get_static_pad(queue, "sink")
    ghost_pad = Gst.GhostPad.new("sink", sink_pad)
    if not udpsinkbin.add_pad(ghost_pad):
        logger.error("Failed to add ghost pad to udpsinkbin")
        return None

    """
    Note:
    you can use this for testing on the recicinv end! (set the IP correctly, my pc is 172.16.1.11)
    ```
    gst-launch-1.0 -v udpsrc port=6003 caps="application/x-rtp, media=(string)video, clock-rate=(int)90000, encoding-name=(string)H265" ! rtph265depay ! h265parse ! avdec_h265 ! videoconvert ! autovideosink
    ```
    """
    app_context.set_value('udp_sink_bin', udpsinkbin)
    return 0

def create_multi_argus_camera_bin(cameras, app_context=app_context):
    """
    Create a multi argus camera bin
    """
    logger = app_context.get_value('app_context_v2').logger
    capture_tests = [camera for camera in cameras if camera['detected_on_init'] == True]
    num_capture_test_passed_cameras = len([camera for camera in capture_tests if camera.get('capture_test_passed') == True])
    logger.debug(f'number of cameras that passed the capture test: {num_capture_test_passed_cameras}')
    csi_enabled = app_context.get_value('enable_csi')
    csi_camera_list = ['front', 'rear']
    number_of_sources = num_capture_test_passed_cameras
    is_filesrc = False
    display_width = 1920
    display_height = 1080
    logger.debug(f'display properties: width: {display_width}, height: {display_height}')
    num_created_srcbins = 0
    muxer_padmap = {}
    camera_settings_overrides = app_context.get_value('camera_settings_overrides')
    probe_ids = app_context.get_value('probe_ids')

    multi_nvargus_bin = Gst.Bin.new('multi_nvargus_bin')
    streammux = make_element('nvstreammux', 'multi_nvargus_streammux')
    
    multi_nvargus_bin.set_property('message-forward', True)
    streammux.set_property('batch-size', number_of_sources)
    streammux.set_property('live-source', 1)
    streammux.set_property('batched-push-timeout', 4000000)
    streammux.set_property('enable-padding', 1)
    logger.debug(f'setting streammux properties to display four cameras: width: {display_width / 2}, height: {display_height / 2}')
    streammux.set_property('width', display_width / 2)
    streammux.set_property('height', display_height / 2)

    Gst.Bin.add(multi_nvargus_bin, streammux)
    
    for i, camera in enumerate(cameras):
        if camera['detected_on_init'] == False:
            logger.debug(f"skipping camera with index {i}, camera name: {camera['name']}, not detected on init")

        elif camera['capture_test_passed'] == False:
            logger.debug(f"skipping camera with index {i}, camera name: {camera['name']}, failed capture test")

        else:
            logger.debug(f"creating camera source for list index {i}, camera name: {camera['name']}")
            device_path = camera['device_path']
            sensor_id = int(device_path.split('/dev/video')[-1])
            camera_blacklist = ['cab', 'roof', 'sky']

            if sensor_id not in [0, 1, 2, 3, 4, 5, 6, 7] or camera['name'] in camera_blacklist or camera['capture_test_passed'] != True:
                logger.debug(f'skipping camera with sensor id: {sensor_id} and camera index: {i}')
                logger.debug(f"!!!skipping camera with sensor id: {sensor_id} and camera index: {i} | camera name: {camera['name']}, capture test passed: {camera['capture_test_passed']}, camera is in the blacklist: {camera['name'] in camera_blacklist}!!!")
                number_of_sources -= 1

            else:
                camera_bin = Gst.Bin.new(f"{camera['name']}_camera_bin")
                if not camera_bin:
                    logger.error(f"failed to create camera bin for camera {camera['name']}")
                    return 1
                camera_bin.set_property('message-forward', True)
                camera_name = camera['name']
                camera_config = {'gainrange': camera['gainrange'], 'exposuretimerange': camera['exposuretimerange'], 'ispdigitalgainrange': camera['ispdigitalgainrange'], 'sensor-mode': camera['sensor_mode']}
                logger.debug(f"camera index: {i}, camera name: {camera['name']}, sensor id: {sensor_id}")
                logger.debug(f"checkigng for settings overrides for {camera['name']}")
                override = False

                if camera_name in camera_settings_overrides:
                    logger.debug('camera settings overrides are set, using them')
                    logger.debug(f'camera settings overrides: {camera_settings_overrides[camera_name]}')
                    override_dict = camera_settings_overrides[camera_name]
                    override = override_dict.get('override', False)
                    codec = override_dict.get('codec', 'h264')
                    file_path = override_dict.get('file_path', None)

                else:
                    logger.debug(f'camera settings overrides are not set for camera {camera_name}, using default settings')

                if override == True:
                    override = False
                    logger.debug(f"creating filesrc substiture for camera {camera['name']} at {file_path}")
                    camera_source = make_bucher_ds_filesrc(file_path, codec, app_context)
                    is_filesrc = True

                    if camera_source:
                        logger.debug(f"file source created for camera {camera['name']}")
                        is_filesrc = True

                else:
                    logger.debug(f'creating argus camera source for sensor id: {sensor_id}')
                    camera_source = make_argus_camera_source(int(sensor_id), camera_config)
                    camera_source.set_property('name', f"{camera['name']}_camera_source")
                    source_pad = camera_source.get_static_pad('src')
                    if source_pad:
                        probe_id = source_pad.add_probe(Gst.PadProbeType.BUFFER, buffer_monitor_probe, camera_name)
                        probe_ids[f"{camera['name']}"]['buffer_monitor'] = probe_id

                    else:
                        print('Failed to get source pad')

                converter_compute_hw = camera['converter_compute_hw'] if camera['converter_compute_hw'] != 'default' else 0
                converter_qos = camera['qos'] if camera['qos'] != 'default' else False
                converter_src_crop = camera['converter_src_crop'] if camera['converter_src_crop'] != 'default' else '0:0:0:0'
                converter_dst_crop = camera['converter_dst_crop'] if camera['converter_dst_crop'] != 'default' else '0:0:0:0'
                converter_flip_method = camera['converter_flip_method'] if camera['converter_flip_method'] != 'default' else 0
                logger.debug(f"setting nvvideoconvert properties for camera {camera['name']}")
                logger.debug(f'converter_compute_hw: {converter_compute_hw}')
                logger.debug(f'converter_flip_method: {converter_flip_method}')
                logger.debug(f'converter_QOS: {converter_qos}')
                
                convert = make_element('nvvideoconvert', f"nvvidconv_{camera['name']}")

                convert.set_property('name', f"{camera['name']}_camera_nvvidconv")
                convert.set_property('qos', converter_qos)
                if converter_dst_crop != '0:0:0:0':
                    logger.debug(f'converter_dst_crop: "{converter_dst_crop}"')
                    convert.set_property('dst-crop', f'{converter_dst_crop}')

                else:
                    logger.debug('skipping dst-crop, using default value')

                if converter_src_crop != '0:0:0:0':
                    logger.debug(f'converter_src_crop: "{converter_src_crop}"')
                    convert.set_property('src-crop', f'{converter_src_crop}')

                else:
                    logger.debug('skipping src-crop, using default value')
            
                logger.debug(f'^^^^^^^^^^^^^^^^^^^^ isfilesrc: {is_filesrc} ^')
                if is_filesrc != True:
                    logger.debug(f'setting flip method for camera {camera_name} to {converter_flip_method}')
                    convert.set_property('flip-method', converter_flip_method)
                    is_filesrc = False

                streammux_pad_index_for_source = i
                muxer_padmap[f'{streammux_pad_index_for_source}'] = i
                logger.debug(f"camera index: {i}, device path: {device_path}, device tree node id: {camera['device_tree_node_id']}, target muxer pad index: {streammux_pad_index_for_source}")

                Gst.Bin.add(camera_bin, camera_source)
                Gst.Bin.add(camera_bin, convert)
                Gst.Bin.add(multi_nvargus_bin, camera_bin)

                camera_source.link(convert)
                camera_bin.add_pad(Gst.GhostPad.new('src', get_static_pad(convert, 'src')))
                
                link_static_srcpad_pad_to_request_sinkpad(camera_bin, streammux, sink_pad_index=streammux_pad_index_for_source)
                num_created_srcbins += 1

    else:
        app_context.set_value('muxer_padmap', muxer_padmap)
        logger.debug(f'muxer pad map: {muxer_padmap}')
        streammux.set_property('batch-size', num_created_srcbins)
        multi_nvargus_bin.add_pad(Gst.GhostPad.new('src', streammux.get_static_pad('src')))
        app_context.set_value('multi_argus_camera_bin', multi_nvargus_bin)
        return 0

def override_monitoring():
    """Monitor override state from CAN server"""
    pipeline = app_context.get_value('pipeline')
    previous_override_state = None
    initialized = None
    app_context.set_value('recording_state', 0)
    can_client = app_context.get_value('can_client')
    while True:
        try:
            if can_client.connected:
                response = can_client.get_override_state()
                if response['status'] == 'success':
                    override_state = response['override_state']
                    current_override_state = override_state
                    if previous_override_state is not None and current_override_state != previous_override_state:
                        if not initialized:
                            initialize_recording(pipeline)
                            initialized = True
                        if current_override_state == 1 and initialized:
                            print('Override state changed to ON')
                            if app_context.get_value('recording_state') == 0:
                                start_recording(pipeline)
                        elif current_override_state == 0 and initialized:
                            print('Override state changed to OFF')
                            if app_context.get_value('recording_state') == 1:
                                stop_recording(pipeline)
                    previous_override_state = current_override_state
                else:
                    print(f'Error getting override state: {response}')
        except Exception as e:
            print(f'Error monitoring override state: {e}')
        time.sleep(0.5)

def initialize_recording(pipeline):
    valve = pipeline.get_by_name('overide_valve')
    valve.set_property('drop', False)
    app_context.set_value('recording_state', 1)

def stop_recording(pipeline):
    time.sleep(20)
    hr_output_bin = pipeline.get_by_name('hr_output_bin')
    valve = pipeline.get_by_name('overide_valve')
    if valve:
        valve.set_property('drop', True)
        print(f"Valve drop property: {valve.get_property('drop')}")
    splitmuxsink = pipeline.get_by_name('overide_splitmux')
    if splitmuxsink:
        sinkpad = splitmuxsink.get_static_pad('video')
        if sinkpad:
            time.sleep(0.5)
            sinkpad.send_event(Gst.Event.new_eos())
            time.sleep(1.0)
            splitmuxsink.set_state(Gst.State.NULL)
            hr_output_bin.remove(splitmuxsink)
            app_context.set_value('recording_state', 0)
            print('Recording stopped cleanly')
        else:
            print('Warning: Could not find video sink pad')
    else:
        print('Warning: No active recording splitmuxsink found')

def start_recording(pipeline):
    hr_output_bin = pipeline.get_by_name('hr_output_bin')
    valve = pipeline.get_by_name('overide_valve')
    if not valve:
        print('Warning: Could not find valve element')
        return
    old_splitmuxsink = pipeline.get_by_name('overide_splitmux')
    if old_splitmuxsink:
        print('Found existing splitmuxsink, removing it first')
        old_splitmuxsink.set_state(Gst.State.NULL)
        hr_output_bin.remove(old_splitmuxsink)
    timestamp = datetime.now().strftime('%Y_%m_%d_%H%M')
    new_splitmuxsink = make_element('splitmuxsink', 'overide_splitmux')
    if not new_splitmuxsink:
        print('Error: Failed to create new splitmuxsink element')
        return
    new_splitmuxsink.set_property('max-size-time', int('1200000000000'))
    logfile = f'/mnt/syslogic_sd_card/upload/override@{timestamp}'
    new_splitmuxsink.set_property('location', f'{logfile}_%d.h265')
    new_splitmuxsink.set_property('async-handling', True)
    new_splitmuxsink.set_property('muxer-factory', 'matroskamux')
    new_splitmuxsink.set_property('alignment-threshold', 1000000000)
    new_splitmuxsink.set_property('start-index', 0)
    hr_output_bin.add(new_splitmuxsink)
    overide_valve = pipeline.get_by_name('overide_valve')
    if not overide_valve:
        print('Error: Could not find overide_valve element')
        hr_output_bin.remove(new_splitmuxsink)
        return
    if not overide_valve.link(new_splitmuxsink):
        print('Error: Failed to link overide_valve to new splitmuxsink')
        hr_output_bin.remove(new_splitmuxsink)
        return
    state_return = new_splitmuxsink.sync_state_with_parent()
    if state_return != Gst.StateChangeReturn.SUCCESS:
        print(f'Warning: sync_state_with_parent returned {state_return}')
    time.sleep(0.5)
    valve.set_property('drop', False)
    print(f"Valve drop property: {valve.get_property('drop')}")
    app_context.set_value('recording_state', 1)
    print(f'Recording started to {logfile}')

def create_hr_output_bin(app_context):
    logger = app_context.get_value('app_context_v2').logger
    enhanced_logging = app_context.get_value('enhanced_logging')
    num_sources = app_context.get_value('num_sources')
    log_directory = app_context.get_value('log_directory')
    serial_number = app_context.get_value('serial_number')
    file_start_time = app_context.get_value('file_start_time')
    log_duration = app_context.get_value('log_duration')
    hr_output_bin = Gst.Bin.new('hr_output_bin')
    hr_output_bin.set_property('message-forward', False)
    queue_filesink = make_element('queue', 'queue_filesink')
    clear_convert = make_element('nvvideoconvert', 'clear_convert')
    clear_tiler = make_element('nvmultistreamtiler', 'clear_tiler')
    clear_encoder = make_element('nvv4l2h265enc', 'clear_encoder')
    clear_parser = make_element('h265parse', 'clear_parser')
    overide_splitmux = make_element('splitmuxsink', 'overide_splitmux')
    post_encode_queue = make_element('queue', 'post_encode_queue')
    overide_valve = make_element('valve', 'overide_valve')
    tee = make_element('tee', 'overide_tee')
    clear_queue = make_element('queue', 'clear_queue')
    clear_splitmux = make_element('splitmuxsink', 'clear_splitmux')
    elements = [queue_filesink, clear_convert, clear_tiler, clear_encoder, clear_parser, overide_valve, post_encode_queue, overide_splitmux, tee, clear_queue, clear_splitmux]
    for element in elements:
        if not element:
            logger.error(f'Failed to create element: {element}')
            return 1
    else:
        queue_filesink.set_property('leaky', 2)
        queue_filesink.set_property('max-size-buffers', 300)
        queue_filesink.set_property('flush-on-eos', True)
        clear_tiler_rows = 2
        tiler_columns = 2
        clear_tiler_width = 3840
        clear_tiler_height = 2160
        clear_tiler.set_property('rows', clear_tiler_rows)
        clear_tiler.set_property('columns', tiler_columns)
        clear_tiler.set_property('width', clear_tiler_width)
        clear_tiler.set_property('height', clear_tiler_height)
        clear_encoder.set_property('bitrate', 6000000 * num_sources)
        clear_encoder.set_property('insert-sps-pps', 1)
        clear_encoder.set_property('qos', True)
        clear_queue.set_property('leaky', 2)
        clear_queue.set_property('max-size-buffers', 30)
        clear_queue.set_property('flush-on-eos', True)
        if not enhanced_logging:
            overide_valve.set_property('drop', True)
        post_encode_queue.set_property('leaky', 2)
        post_encode_queue.set_property('max-size-buffers', 0)
        post_encode_queue.set_property('max-size-bytes', 0)
        post_encode_queue.set_property('max-size-time', 10000000000)
        post_encode_queue.set_property('min-threshold-time', 10000000000)
        post_encode_queue.set_property('flush-on-eos', True)
        logfile = f'{log_directory}{serial_number}_{file_start_time}'
        overide_splitmux.set_property('max-size-time', int(f'{log_duration}000000000'))
        if not enhanced_logging:
            timestamp = datetime.now().strftime('%Y_%m_%d_%H%M')
            logfile = f'/mnt/syslogic_sd_card/upload/override@{timestamp}'
        else:
            logfile = f'{log_directory}/upload/{serial_number}_{file_start_time}'
        overide_splitmux.set_property('location', f'{logfile}_%d.h265')
        overide_splitmux.set_property('async-handling', True)
        clear_splitmux.set_property('max-size-time', int(f'{log_duration}000000000'))
        logfile = f'/mnt/syslogic_sd_card/{serial_number}_{file_start_time}'
        clear_splitmux.set_property('location', f'{logfile}_%d.h265')
        clear_splitmux.set_property('async-handling', True)
        for element in elements:
            try:
                hr_output_bin.add(element)
            except Exception as e:
                logger.error(f'Failed to add element {element.get_name()}: {e}')
                return 1
        if not (queue_filesink.link(clear_convert) and
            clear_convert.link(clear_tiler) and
            clear_tiler.link(clear_encoder) and
            clear_encoder.link(clear_parser) and
            clear_parser.link(tee) and
            post_encode_queue.link(overide_valve) and
            clear_queue.link(clear_splitmux) and
            overide_valve.link(overide_splitmux)):
            logger.error('Elements could not be linked.')
            return 1
        link_request_srcpad_to_static_sinkpad(tee, post_encode_queue, src_pad_index=0)
        link_request_srcpad_to_static_sinkpad(tee, clear_queue, src_pad_index=1)
        sink_pad = get_static_pad(queue_filesink, 'sink')
        ghost_pad = Gst.GhostPad.new('sink', sink_pad)
        if not hr_output_bin.add_pad(ghost_pad):
            logger.error('Failed to add ghost pad to udpsinkbin')
            return
        return hr_output_bin

def debug_element_connections(element, logger):
    """Debug function to check what an element is connected to"""
    element_name = element.get_name()
    logger.debug(f'\n=== Debugging connections for: {element_name} ===')
    sink_pad = element.get_static_pad('sink')
    if sink_pad:
        peer = sink_pad.get_peer()
        if peer:
            peer_element = peer.get_parent_element()
            logger.debug(f'  Sink pad connected to: {peer_element.get_name()}:{peer.get_name()}')
        else:
            logger.debug('  Sink pad NOT connected')
    src_pad = element.get_static_pad('src')
    if src_pad:
        peer = src_pad.get_peer()
        if peer:
            peer_element = peer.get_parent_element()
            logger.debug(f'  Src pad connected to: {peer_element.get_name()}:{peer.get_name()}')
        else:
            logger.debug('  Src pad NOT connected')
    logger.debug('==================================================')

def create_bucher_inference_bin(app_context=app_context):
    """
    Create a bucher inference bin
    """
    logger = app_context.get_value('app_context_v2').logger
    config_paths_dict_ = app_context.get_value('config_paths')

    preprocess_config_file_path = config_paths_dict_.get('preprocess', None)['path']
    preprocess_config_draw_roi = config_paths_dict_.get('preprocess', None)['draw-roi']
    preprocess_config_roi_params_src_0 = config_paths_dict_.get('preprocess', None)['roi-params-src-0']
    preprocess_config_network_input_shape = config_paths_dict_.get('preprocess', None)['network-input-shape']

    infer_config_file_path = config_paths_dict_.get('inference', None)['path']
    infer_config_model_engine_file = config_paths_dict_.get('inference', None)['model-engine-file']
    infer_config_labelfile_path = config_paths_dict_.get('inference', None)['labelfile-path']
    infer_config_input_tensor_from_meta = config_paths_dict_.get('inference', None)['input-tensor-from-meta']
    infer_config_infer_dims = config_paths_dict_.get('inference', None)['infer-dims']

    modify_deepstream_config_files(preprocess_config_file_path, preprocess_config_file_path, 'group-0', 'draw-roi', preprocess_config_draw_roi, app_context)
    modify_deepstream_config_files(preprocess_config_file_path, preprocess_config_file_path, 'group-0', 'roi-params-src-0', preprocess_config_roi_params_src_0, app_context)
    modify_deepstream_config_files(preprocess_config_file_path, preprocess_config_file_path, 'property', 'network-input-shape', preprocess_config_network_input_shape, app_context)
    modify_deepstream_config_files(infer_config_file_path, infer_config_file_path, 'property', 'model-engine-file', infer_config_model_engine_file, app_context)
    modify_deepstream_config_files(infer_config_file_path, infer_config_file_path, 'property', 'labelfile-path', infer_config_labelfile_path, app_context)
    modify_deepstream_config_files(infer_config_file_path, infer_config_file_path, 'property', 'input-tensor-from-meta', infer_config_input_tensor_from_meta, app_context)
    modify_deepstream_config_files(infer_config_file_path, infer_config_file_path, 'property', 'infer-dims', infer_config_infer_dims, app_context)

    metamux_config_file_path = config_paths_dict_.get('metamux', None)['path']
    cameras = app_context.get_value('init_config')['cameras']
    num_sources = len([camera for camera in cameras if camera.get('capture_test_passed') == True])
    app_context.set_value('num_sources', num_sources)
    inference_bin = Gst.Bin.new('bucher_inference_bin')
    if not inference_bin:
        logger.error('Failed to create parent bucher_inference_bin')
        return 1
    inference_bin.set_property('message-forward', True)
    inference_bin_tee = make_element('tee', 'inference_bin_tee')
    Gst.Bin.add(inference_bin, inference_bin_tee)
    inference_bin.add_pad(Gst.GhostPad.new('sink', get_static_pad(inference_bin_tee, 'sink')))
    metamux = make_element('nvdsmetamux', 'inference_bin_metamux')
    metamux.set_property('config-file', metamux_config_file_path)
    videomux = make_element('nvstreammux', 'videomux')
    videomux.set_property('batch-size', num_sources)
    videomux.set_property('live-source', 1)
    videomux.set_property('batched-push-timeout', 33000000)
    videomux.set_property('width', 960)
    videomux.set_property('height', 540)
    Gst.Bin.add(inference_bin, videomux)
    Gst.Bin.add(inference_bin, metamux)
    inference_bin.add_pad(Gst.GhostPad.new('src', get_static_pad(metamux, 'src')))
    queue_to_stream_demuxer = make_element('queue', 'queue_to_streamdemuxer')
    Gst.Bin.add(inference_bin, queue_to_stream_demuxer)
    
    hr_output_bin = create_hr_output_bin(app_context)
    Gst.Bin.add(inference_bin, hr_output_bin)
    link_request_srcpad_to_static_sinkpad(inference_bin_tee, hr_output_bin, src_pad_index=0)
    link_request_srcpad_to_static_sinkpad(inference_bin_tee, queue_to_stream_demuxer, src_pad_index=2)

    stream_demuxer = make_element('nvstreamdemux', 'inference_stream_demuxer')
    Gst.Bin.add(inference_bin, stream_demuxer)
    queue_to_stream_demuxer.link(stream_demuxer)
    padmap = app_context.get_value('muxer_padmap')
    num_nozzlet_sources = 0
    num_csi_sources = 0
    camera_blacklist = ['cab']
    nozzlenet_cameras = ['right', 'left']
    csi_cameras = ['front', 'rear']

    csi_merger = make_element('nvstreammux', 'csi_merger')
    csi_merger.set_property('batch-size', 2)
    csi_merger.set_property('live-source', 1)
    csi_merger.set_property('batched-push-timeout', 100000000)
    csi_merger.set_property('width', 960)
    csi_merger.set_property('height', 540)
    csi_merger.set_property('sync-inputs', True)
    Gst.Bin.add(inference_bin, csi_merger)

    for muxer_pad_index, camera_index in padmap.items():
        muxer_pad_index = int(muxer_pad_index)
        camera_index = int(camera_index)
        camera = cameras[camera_index]
        camera_name = camera['name']
        camera_position = camera['position']
        do_inference = camera['do_infer']
        logger.debug(f'[create infernce bin]: camera config index: {camera_index}, camera position: {camera_position}, muxer pad index: {muxer_pad_index}')

        if camera_position in nozzlenet_cameras:
            num_nozzlet_sources += 1
            logger.debug(f'camera position: {camera_position} with name {camera_name} camera is a nozzle view camera')
        if camera_position in csi_cameras:
            num_csi_sources += 1
            logger.debug(f'camera position: {camera_position} camera is a street view camera')
        
        queue_to_streammux = make_element('queue', f'queue_{camera_name}_to_streammux')
        Gst.Bin.add(inference_bin, queue_to_streammux)
        queue_post_streammux = make_element('queue', f'queue_{camera_name}_post_streammux')
        Gst.Bin.add(inference_bin, queue_post_streammux)
        tee = make_element('tee', f'tee_{camera_name}')
        Gst.Bin.add(inference_bin, tee)
        if do_inference:
            queue_to_inference = make_element('queue', f'queue_{camera_name}_to_inference')
            Gst.Bin.add(inference_bin, queue_to_inference)
            link_request_srcpad_to_static_sinkpad(tee, queue_to_inference, src_pad_index=0)
        
        selective_streammux = make_element('nvstreammux', f'selective_streammux_{camera_name}')
        selective_streammux.set_property('batch-size', 1)
        selective_streammux.set_property('live-source', 1)
        selective_streammux.set_property('batched-push-timeout', 4000000)
        selective_streammux.set_property('width', 960)
        selective_streammux.set_property('height', 540)
        Gst.Bin.add(inference_bin, selective_streammux)
        link_request_srcpad_to_static_sinkpad(stream_demuxer, queue_to_streammux, src_pad_index=muxer_pad_index)
        link_static_srcpad_pad_to_request_sinkpad(queue_to_streammux, selective_streammux, sink_pad_index=muxer_pad_index)
        selective_streammux.link(queue_post_streammux)
        queue_post_streammux.link(tee)
        
        if camera['position'] in nozzlenet_cameras:
            queue_to_videomux = make_element('queue', f'queue_{camera_name}_to_videomux')
            Gst.Bin.add(inference_bin, queue_to_videomux)
            link_request_srcpad_to_static_sinkpad(tee, queue_to_videomux, src_pad_index=1)
            link_static_srcpad_pad_to_request_sinkpad(queue_to_videomux, videomux, sink_pad_index=muxer_pad_index)
        if camera['position'] in csi_cameras:
            queue_to_inference.set_property('max-size-buffers', 1)
            queue_to_inference.set_property('leaky', 1)
            queue_to_inference.set_property('flush-on-eos', True)
            link_static_srcpad_pad_to_request_sinkpad(queue_to_inference, csi_merger, sink_pad_index=muxer_pad_index)

    logger.debug('demux queues created....')
    logger.debug(f'number of nozzle cameras: {num_nozzlet_sources}')
    logger.debug(f'number of csi cameras: {num_csi_sources}')
    
    if num_nozzlet_sources > 0:

        nozzlenet_infer_bin = Gst.Bin.new('BUCHER-nozzlenet-infer-bin')
        pgie = make_element('nvinfer', 'nozzlenet-infer')
        nozzlenet_infer_placeholder = make_element('identity', 'nozzlenet_infer_placeholder')
        preprocess = make_element('nvdspreprocess', 'nozzlenet_preprocess')
        nvvideo_conv_readjuster = make_element('nvvideoconvert', 'resize-back-to-fit-display')
        caps_filter_readjuster = make_element('capsfilter', 'capsfilter')
        queue_nozzlenet_post_infer = make_element('queue', 'queue_nozzlenet_post_infer')
        
        elements = [pgie, nozzlenet_infer_placeholder, preprocess, nvvideo_conv_readjuster, caps_filter_readjuster, queue_nozzlenet_post_infer]
        
        tracker_src_pad = get_static_pad(pgie, 'src')
        primary_inference_queue = inference_bin.get_by_name(f'queue_primary_nozzle_to_inference')
        
        nozzlenet_infer_bin.set_property('message-forward', True)
        preprocess.set_property('config-file', preprocess_config_file_path)
        pgie.set_property('config-file-path', infer_config_file_path)
        pgie.set_property('unique-id', 1)
        caps_filter_readjuster.set_property('caps', Gst.Caps.from_string('video/x-raw(memory:NVMM), width=960, height=540'))
        queue_nozzlenet_post_infer.set_property('leaky', 'downstream')

        Gst.Bin.add(inference_bin, nozzlenet_infer_bin)
        for element in elements:
            try:
                Gst.Bin.add(nozzlenet_infer_bin, element)
            except Exception as e:
                logger.error(f"Error adding element {element.get_name()} to nozzlenet_infer_bin: {e}")
       
        nozzlenet_infer_placeholder.link(preprocess)
        preprocess.link(pgie)
        pgie.link(nvvideo_conv_readjuster)
        nvvideo_conv_readjuster.link(caps_filter_readjuster)
        caps_filter_readjuster.link(queue_nozzlenet_post_infer)
        nozzlenet_infer_bin.add_pad(Gst.GhostPad.new('src', get_static_pad(queue_nozzlenet_post_infer, 'src')))
        tracker_src_pad.add_probe(Gst.PadProbeType.BUFFER, lambda pad, info, u_data: nozzlenet_src_pad_buffer_probe(pad, info, u_data), 0)
        primary_inference_queue.link(nozzlenet_infer_placeholder)       

    if num_csi_sources > 0:
        
        flip_method = camera['converter_flip_method'] if camera['converter_flip_method'] != 'default' else 0
        csi_probe_bin = create_csiprobebin(app_context, flip_method)

        csi_demuxer = make_element('nvstreamdemux', 'csi_demuxer')
        csi_front_videorate_queue = make_element('queue', 'csi_front_videorate_queue')
        csi_rear_videorate_queue = make_element('queue', 'csi_rear_videorate_queue')
        csi_front_videomux_queue = make_element('queue', 'csi_front_videomux_queue')
        csi_rear_videomux_queue = make_element('queue', 'csi_rear_videomux_queue')
        csi_front_videorate = make_element('videorate', 'csi_front_videorate')
        csi_rear_videorate = make_element('videorate', 'csi_rear_videorate')

        csi_bin_srcpad_0 = csi_probe_bin.get_static_pad('src_0')
        csi_demuxer_sinkpad = csi_demuxer.get_static_pad('sink')

        csi_front_videomux_queue.set_property('max-size-buffers', 2)
        csi_rear_videomux_queue.set_property('max-size-buffers', 2)
        csi_front_videomux_queue.set_property('leaky', 2)
        csi_rear_videomux_queue.set_property('leaky', 2)
        csi_front_videomux_queue.set_property('flush-on-eos', True)
        csi_rear_videomux_queue.set_property('flush-on-eos', True)
        csi_front_videorate_queue.set_property('max-size-buffers', 2)
        csi_rear_videorate_queue.set_property('max-size-buffers', 2)
        csi_front_videorate_queue.set_property('leaky', 2)
        csi_rear_videorate_queue.set_property('leaky', 2)
        csi_front_videorate_queue.set_property('flush-on-eos', True)
        csi_rear_videorate_queue.set_property('flush-on-eos', True)
        csi_front_videorate.set_property('skip-to-first', True)
        csi_rear_videorate.set_property('skip-to-first', True)
        
        Gst.Bin.add(inference_bin, csi_probe_bin)
        Gst.Bin.add(inference_bin, csi_demuxer)
        Gst.Bin.add(inference_bin, csi_front_videorate_queue)
        Gst.Bin.add(inference_bin, csi_rear_videorate_queue)
        Gst.Bin.add(inference_bin, csi_front_videomux_queue)
        Gst.Bin.add(inference_bin, csi_rear_videomux_queue)
        Gst.Bin.add(inference_bin, csi_front_videorate)
        Gst.Bin.add(inference_bin, csi_rear_videorate)
        
        csi_merger.link(csi_probe_bin)
        csi_bin_srcpad_0.link(csi_demuxer_sinkpad)
        link_request_srcpad_to_static_sinkpad(csi_demuxer, csi_front_videorate_queue, src_pad_index=0)
        link_request_srcpad_to_static_sinkpad(csi_demuxer, csi_rear_videorate_queue, src_pad_index=2)
        csi_front_videorate_queue.link(csi_front_videorate)
        csi_rear_videorate_queue.link(csi_rear_videorate)
        csi_front_videorate.link(csi_front_videomux_queue)
        csi_rear_videorate.link(csi_rear_videomux_queue)
        link_static_srcpad_pad_to_request_sinkpad(csi_front_videomux_queue, videomux, sink_pad_index=0)
        link_static_srcpad_pad_to_request_sinkpad(csi_rear_videomux_queue, videomux, sink_pad_index=2)
        link_static_srcpad_pad_to_request_sinkpad(videomux, metamux, sink_pad_index=0)
        link_static_srcpad_pad_to_request_sinkpad(nozzlenet_infer_bin, metamux, sink_pad_index=1)

    app_context.set_value('bucher_inference_bin', inference_bin)
    return 0

def main(args):
    logger = app_context.get_value('app_context_v2').logger

    # Runtime variable setup
    state_machine = SmartStateMachine()
    can_client = CanClient(client_name='pipeline_w_logging.py')
    logging_config = Configuration()
    serial_number = logging_config.get_serial_number()
    log_duration = logging_config.get_log_duration()
    columns = logging_config.get_camera_columns()
    csi_columns = logging_config.get_csi_columns()
    log_directory = logging_config.get_directory()
    file_start_time = datetime.now().strftime('%Y_%m_%d_%H%M')
    probe_ids = {'primary_nozzle': {'buffer_monitor': None}, 'secondary_nozzle': {'buffer_monitor': None}, 'front': {'buffer_monitor': None, 'csi_probe': None}, 'rear': {'buffer_monitor': None, 'csi_probe': None}}
    search_item_list = [DETECTION_CATEGORIES.PGIE_CLASS_ID_ACTION_OBJECT.value, DETECTION_CATEGORIES.PGIE_CLASS_ID_CHECK_NOZZLE.value, DETECTION_CATEGORIES.PGIE_CLASS_ID_NOZZLE_BLOCKED.value, DETECTION_CATEGORIES.PGIE_CLASS_ID_NOZZLE_CLEAR.value, DETECTION_CATEGORIES.PGIE_CLASS_ID_GRAVEL.value]
    full_path_and_filename = __file__
    socket_path = '/tmp/bucher-deepstream-python-logger.sock'
    nn_fps_counter = GETFPS(0)
    rear_csi_fps_counter = GETFPS(0)
    front_csi_fps_counter = GETFPS(0)
    overlay_parts = {'sm_nozzle_state': 0, 'sm_fan_speed': 0, 'sm_current_status': 'N/A', 'sm_current_state': 'N/A', 'sm_time_difference': 0, 'sm_ao_status': 'N/A', 'sm_ao_difference': 0, 's1_pm10': 'N/A', 's2_pm10': 'N/A', 's3_pm10': 'N/A', 's4_pm10': 'N/A', 's5_pm10': 'N/A'}
    stop_event = threading.Event()
    monitoring_thread = threading.Thread(target=override_monitoring, daemon=True)
    overlay_thread = threading.Thread(target=overlay_parts_fetcher, daemon=True)
    server_thread = threading.Thread(target=unix_socket_server, args=('/tmp/smart_sweeper_pipeline_comms_socket', stop_event))

    # Store runtime variables in app context
    app_context.set_value('shutdown_initiated_by_user_process', False)
    app_context.set_value('pid_path', '/tmp/bucher-deepstream-python-logger.pid')
    app_context.set_value('last_notificationsent_to_systemd', '')
    app_context.set_value('enhanced_logging', False)
    app_context.set_value('can_client', can_client)
    app_context.set_value('state_machine', state_machine)
    app_context.set_value('serial_number', serial_number)
    app_context.set_value('log_duration', log_duration) 
    app_context.set_value('camera_columns', columns)
    app_context.set_value('csi_columns', csi_columns)
    app_context.set_value('log_directory', log_directory)
    app_context.set_value('file_start_time', file_start_time)
    app_context.set_value('probe_ids', probe_ids)
    app_context.set_value('search_item_list', search_item_list)
    app_context.set_value('full_path_and_filename', full_path_and_filename)
    app_context.set_value('socket_path', socket_path)
    app_context.set_value('nn_fps_counter', nn_fps_counter)
    app_context.set_value('rear_csi_fps_counter', rear_csi_fps_counter)
    app_context.set_value('front_csi_fps_counter', front_csi_fps_counter)
    app_context.set_value('overlay_parts', overlay_parts)
    app_context.set_value('monitoring_thread', monitoring_thread)
    app_context.set_value('overlay_thread', overlay_thread)
    app_context.set_value('server_thread', server_thread)
    app_context.set_value('stop_event', stop_event)

    if os.path.isfile('/etc/systemd/system/nvargus-daemon.service'):
        logger.debug('nvargus-daemon.service file exists, restarting it..')
        notify_systemd('STATUS=restarting argus daemon')
        subprocess.call(['sudo', 'systemctl', 'restart', 'nvargus-daemon.service'])
    else:
        logger.debug('nvargus-daemon.service file does not exist')
    
    notify_systemd('STATUS=INITIALIZING_GSTREAMER_ELEMENTS')
    
    GObject.threads_init()
    logger.debug('logger initialized in main..')
    init_config = app_context.get_value('init_config')
    logger.debug(f'init_config: {init_config}')
    cameras = init_config.get('cameras', None)
    
    # Pipeline creation
    logger.debug("creating GST pipeline..")
    pipeline = Gst.Pipeline()
    display_width = init_config['display_width']
    display_height = init_config['display_height']
    tiler_rows = 2
    tiler_columns = 2
    tiler_width = int(display_width)
    tiler_height = int(display_height)
    
    logger.debug('adding multi_argus_camera_bin to the pipeline..')
    multi_src_bin_ok = create_multi_argus_camera_bin(cameras, app_context)
    if multi_src_bin_ok != 0:
        logger.error('failed to create multi source bin')
        return -1
    multi_argus_camera_bin = app_context.get_value('multi_argus_camera_bin')

    logger.debug('adding bucher_inference_bin to the pipeline..')
    inference_bin_ok = create_bucher_inference_bin(app_context)
    if inference_bin_ok != 0:
        logger.error('failed to create bucher inference bin')
        return -1
    inference_bin = app_context.get_value('bucher_inference_bin')

    logger.debug('adding udp_sink_bin to the pipeline..')
    udp_sink_bin_ok = create_udpsinkbin(app_context)
    if udp_sink_bin_ok != 0:
        logger.error('failed to create udp sink bin')
        return -1
    udp_sink_bin = app_context.get_value('udp_sink_bin')

    tiler = make_element('nvmultistreamtiler', 'display-tiler')
    nvvidconv = make_element('nvvideoconvert', 1)
    nvosd = make_element('nvdsosd')
    rtsp_sink_queue = make_element('queue', 'rtsp_sunk_queue')

    logger.debug('Setting properties for the elements..')
    tiler.set_property('rows', tiler_rows)
    tiler.set_property('columns', tiler_columns)
    tiler.set_property('width', tiler_width)
    tiler.set_property('height', tiler_height)
    rtsp_sink_queue.set_property('max-size-buffers', 30)
    rtsp_sink_queue.set_property('leaky', 2)
    rtsp_sink_queue.set_property('flush-on-eos', True)
    
    logger.debug('Adding elements to the pipeline..')
    pipeline.add(multi_argus_camera_bin)
    pipeline.add(inference_bin)
    pipeline.add(tiler)
    pipeline.add(nvvidconv)
    pipeline.add(nvosd)
    pipeline.add(rtsp_sink_queue)
    pipeline.add(udp_sink_bin)

    logger.debug('Linking elements in the pipeline..')
    notify_systemd('STATUS=linking static gstreamer elements')
    multi_argus_camera_bin.link(inference_bin)
    inference_bin.link(nvvidconv)
    nvvidconv.link(tiler)
    tiler.link(nvosd)
    nvosd.link(rtsp_sink_queue)
    rtsp_sink_queue.link(udp_sink_bin)

    logger.debug('Setting pipeline and main loop in app context..')
    app_context.set_value('pipeline', pipeline)
    bus = pipeline.get_bus()
    bus.add_signal_watch()
    loop = GObject.MainLoop()
    app_context.set_value('main_loop', loop)
    bus.connect('message', bus_call, loop)
    ctrl_c_count = [0]

    def signal_handler(sig, frame):
        logger.debug('############### CTRL+C pressed ##########################')
        pipeline = app_context.get_value('pipeline')
        ctrl_c_count[0] += 1
        pass
        if ctrl_c_count[0] == 1:
            pass
            can_client = app_context.get_value('can_client')
            can_client.stop_logging()
            can_client.disconnect()
            mt = app_context.get_value('monitoring_thread')
            mt.join(timeout=0.1)
            timestamp = datetime.now().strftime('%Y_%m_%d_%H_%M_%S')
            logger.debug(f"dot file path relative to this script dir -> {os.environ.get('GST_DEBUG_DUMP_DOT_DIR')}/python_ROI_{timestamp}.dot")
            Gst.debug_bin_to_dot_file(pipeline, Gst.DebugGraphDetails.ALL, f'python_{timestamp}')
            logger.debug("******making a symlink to the latest dot file at {os.environ.get('GST_DEBUG_DUMP_DOT_DIR')}/python_ROI_latest.dot ")
            os.system(f"/usr/bin/ln -sf {os.environ.get('GST_DEBUG_DUMP_DOT_DIR')}/python_ROI_{timestamp}.dot {os.environ.get('SCRIPT_EXECUTION_DIR')}/python_nozzlenet_latest.dot")
            naptime.sleep(1)
            app_context.set_value('shutdown_initiated_by_user_process', True)
            logger.debug('sending EOS event to the pipeline')
            streammux = pipeline.get_by_name('multi_nvargus_streammux')
            replaced_pads = app_context.get_value('replacement_pads')
            if replaced_pads:
                for pad in replaced_pads:
                    sink_pad = streammux.get_static_pad(f'{pad}')
                    sink_pad.send_event(Gst.Event.new_eos())
            pipeline.send_event(Gst.Event.new_eos())
            Gst.debug_bin_to_dot_file(pipeline, Gst.DebugGraphDetails.ALL, f'python_post_EOS_{timestamp}')
        elif ctrl_c_count[0] >= 1:
            logger.debug('CTRL+C pressed at least twice. forcing exit.')
            notify_systemd('STOPPING=1')
            if pipeline.set_state(Gst.State.NULL) == Gst.StateChangeReturn.FAILURE:
                logger.debug('Failed to stop the pipeline, attempting to kill the process.')
                os.kill(app_context.get_int('main_process_id').value, signal.SIGKILL)
            else:
                logger.debug('pipeline stopped successfully on second CTRL+C press!')
                loop.quit()
        else:
            ctrl_c_count[0] = 2

    signal.signal(signal.SIGINT, signal_handler)
    notify_systemd('STATUS=settig pipeline to PLAYING state')
    pipeline.set_state(Gst.State.PLAYING)
    monitoring_thread.start()
    overlay_thread.start()
    notify_systemd('STATUS=Ready to Roll...')
    notify_systemd('READY=1')
    notify_systemd('STATUS=ROLLING')
    can_client.connect()
    if can_client.connected:
        print('CAN client connected, starting logging...')
        can_client.start_logging()
    else:
        print('Failed to connect to CAN bus, continuing without CAN logging...')
    if app_context.get_value('SSWP_RUN_MODE') == 'SYSTEMD_NOTIFY_SERVICE':
        logger.debug('setting up the custom unix signal handler to capture stop signals')   
        server_thread.start()
    try:
        loop.run()
    except Exception as err:
        print(f'Error: {err}')
    logger.debug('cleanup')
    notify_systemd('STATUS=Stopping...')
    notify_systemd('STOPPING=1')
    if pipeline and pipeline.get_state(Gst.CLOCK_TIME_NONE) != Gst.State.NULL:
        pipeline.set_state(Gst.State.NULL)
    logger.debug(f"app context: shutdown initiated by user process = {app_context.get_boolean('shutdown_initiated_by_user_process').value}")
    logger.debug(f"app context: process_id = {app_context.get_int('main_process_id').value}")
    logger.debug(f"app context: pid_path = {app_context.get_string('pid_path')}")
    app_context.free()
    if app_context.get_value('SSWP_RUN_MODE') == 'SYSTEMD_NOTIFY_SERVICE':
        server_thread.join()
    
if __name__ == '__main__':
    app_context.set_value('main_process_id', os.getpid())
    app_context.set_value('SSWP_RUN_MODE', 'STANDALONE')
    if os.environ.get('SSWP_RUN_MODE') == 'SYSTEMD_NOTIFY_SERVICE':
        app_context.set_value('SSWP_RUN_MODE', os.environ.get('SSWP_RUN_MODE'))
    config_ = Config('/mnt/ssd/csi_pipeline/config/bucher_camera_on_boot_config.json')
    actx_ = AppContext(config_)
    actx_.initialise_logging()
    actx_.logger.debug('starting the camera logger, main process pid: {0}'.format(os.getpid()))
    app_context.set_value('app_context_v2', actx_)
    run_config_file = '/mnt/ssd/csi_pipeline/config/nozzlenet_config.yaml'
    with open(run_config_file, 'r') as yamlfile_:
        run_config = yaml.safe_load(yamlfile_)
    if run_config is None:
        actx_.logger.error('Error loading the run config file, FATAL ERROR, exiting...')
        notify_systemd('STATUS=ERROR')
        sys.exit(1)
    config_paths_dict = {}
    config_paths = run_config.get('ds_configs', None)
    for config_type, configs in config_paths.items():
        config_paths_dict[config_type] = configs
        actx_.logger.debug(f'config_paths_dict[{config_type}] = {configs}')
    essential_config_types = ['preprocess', 'inference', 'metamux', 'tracker']
    for config_type in essential_config_types:
        if config_type not in config_paths_dict:
            actx_.logger.error(f'essential config type {config_type} is missing, FATAL ERROR, exiting...')
            notify_systemd('STATUS=ERROR')
            sys.exit(1)
        if not os.path.isfile(config_paths_dict[config_type]['path']):
            actx_.logger.error(f'essential config file {config_type} not found at {config_paths_dict[config_type]}, FATAL ERROR, exiting...')
            notify_systemd('STATUS=ERROR')
            sys.exit(1)
    app_context.set_value('config_paths', config_paths_dict)
    override_dict = {}
    source_overrides = run_config.get('source_override_parameters', None)
    for source, details in source_overrides.items():
        override = details.get('override', False)
        if override == True:
            name = details.get('name', None)
            actx_.logger.debug(f'overriding source {name} with {details}')
            if name is not None:
                override_dict[name] = details
            else:
                actx_.logger.error(f'source {source} override settings are not valid, skipping..')
    app_context.set_value('camera_settings_overrides', override_dict)
    config_is_csi_enabled = run_config.get('enable_csi', False)
    app_context.set_value('enable_csi', config_is_csi_enabled)
    app_context.set_value('run_config', run_config)
    if load_latest_init_status('bucher_ai_camera_status_on_bucher-d3-camera-init_service_run', app_context) != 0:
        actx_.logger.error('Error loading the latest camera status file, FATAL ERROR, exiting...')
        notify_systemd('STATUS=ERROR')
        sys.exit(1)
    notify_systemd('STATUS=STARTUP')
    notify_systemd('MAINPID={0}'.format(os.getpid()))
    pid_file = os.environ.get('PID_FILE')
    if pid_file is None:
        pid_file = f'/tmp/{os.path.basename(__file__)}.pid'
    if pid_file:
        with open(pid_file, 'w') as f:
            f.write(str(os.getpid()))
            actx_.logger.debug('^^^^^^^^^^^^^^^^^^^^^^^^^pid written to PID_FILE: {0}'.format(pid_file))
            actx_.logger.debug(f"running in {os.environ.get('SSWP_RUN_MODE')} mode, pid: {os.getpid()}")
    else:
        actx_.logger.debug(f"PID_FILE env variable not set, running in {os.environ.get('SSWP_RUN_MODE')} mode, pid: {os.getpid()}")
    actx_.logger.debug('initialising CSI stuff')
    actx_.logger.debug('Initialising the CSI stuff')
    actx_.logger.debug('Creating the inference object and loading the models to gpu')
    sys.exit(main(sys.argv))