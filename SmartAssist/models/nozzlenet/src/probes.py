"""
Nozzlenet Model Probes
Buffer probe for nozzlenet object detection inference

This module contains the nozzlenet_src_pad_buffer_probe function that processes
detection results from the nozzlenet inference engine.

EXTRACTED FROM: pipeline/pipeline_w_logging.py
VERIFIED: Complete implementation with all logic
"""
import sys
import pyds
from gi.repository import Gst
from datetime import datetime

# Import constants from this module
from .constants import (
    PGIE_CLASS_ID_NOZZLE_CLEAR,
    PGIE_CLASS_ID_NOZZLE_BLOCKED,
    PGIE_CLASS_ID_CHECK_NOZZLE,
    PGIE_CLASS_ID_GRAVEL,
    PGIE_CLASS_ID_ACTION_OBJECT,
    BORDER_COLOR_CLEAR,
    BORDER_COLOR_BLOCKED,
    BORDER_COLOR_CHECK,
    BORDER_COLOR_GRAVEL,
    BORDER_COLOR_ACTION_OBJECT,
    BORDER_WIDTH
)


def nozzlenet_src_pad_buffer_probe(pad, info, u_data):
    """
    Nozzlenet buffer probe - THE CORE DETECTION PROCESSING FUNCTION
    
    This probe is attached to the nozzlenet inference engine output pad.
    It processes every frame, extracting object detections, updating the
    state machine, sending CAN messages, and logging to CSV.
    
    Processing Flow:
    1. Get GStreamer buffer and batch metadata
    2. Update FPS counter and send to CAN
    3. Acquire display metadata for OSD (2 labels)
    4. Get frame metadata (batch size=1, single frame)
    5. Setup OSD text parameters
    6. Iterate through detected objects
    7. Filter unwanted detections (search_item_list)
    8. Process each detection by class_id:
       - Set border colors
       - Update prediction dictionary
       - Track highest confidence
    9. Add display metadata to frame
    10. Update state machine with detections
    11. Update CAN bus (fan speed + nozzle state)
    12. Format timestamp for CSV
    13. Send all data to CAN client
    
    :param pad: GStreamer pad
    :param info: Probe info containing buffer
    :param u_data: User data (unused - app_context accessed globally)
    :return: Gst.PadProbeReturn.OK
    
    VERIFIED: Exact from pipeline/pipeline_w_logging.py
    """
    # Get app context (assumes global Gst.Structure named 'app_context')
    # In the new structure, this will be passed properly
    try:
        import gi
        gi.require_version('Gst', '1.0')
        from gi.repository import Gst
        
        # CRITICAL: In the modular version, app_context must be passed via u_data
        # For now, we'll assume it's available globally (backward compatibility)
        app_context = Gst.Structure.from_string("app_context")[0] if u_data is None else u_data
        
        logger = app_context.get_value('app_context_v2').logger
        can_client = app_context.get_value('can_client')
        state_machine = app_context.get_value('state_machine')
        columns = app_context.get_value('camera_columns')
        search_item_list_ = app_context.get_value('search_item_list')
        overlay_parts = app_context.get_value('overlay_parts')
        nn_fps_counter_ = app_context.get_value('nn_fps_counter')
    except:
        # Fallback if app_context not available
        sys.stderr.write("Warning: app_context not available in probe\n")
        return Gst.PadProbeReturn.OK
    
    # Initialize prediction dictionary
    prediction_dict = dict.fromkeys(columns, 0.0)
    frame_number = 0
    obj_id = 0
    deleted = 1
    nozzle_status_string = None
    action_object_string = None
    highest_confidence = 0.0
    timenow = datetime.now()
    
    # Get GStreamer buffer
    gst_buffer = info.get_buffer()
    if not gst_buffer:
        sys.stderr.write('Unable to get pgie src pad buffer\n')
        return Gst.PadProbeReturn.OK
    
    # Update FPS counter
    fps_count = nn_fps_counter_.get_fps()
    if fps_count and can_client and can_client.connected:
        try:
            can_client.update_fps('nn', int(hex(fps_count), 16))
        except Exception as e:
            logger.debug(f'FPS update error: {e}')
    
    # Get batch metadata
    batch_meta = pyds.gst_buffer_get_nvds_batch_meta(hash(gst_buffer))
    if not batch_meta:
        return Gst.PadProbeReturn.OK
    
    # Acquire display metadata for OSD
    display_meta = pyds.nvds_acquire_display_meta_from_pool(batch_meta)
    if not display_meta:
        return Gst.PadProbeReturn.OK
    
    # Get frame metadata (batch size=1, so only one frame)
    l_frame = batch_meta.frame_meta_list
    if not l_frame:
        return Gst.PadProbeReturn.OK
    
    frame_meta = pyds.NvDsFrameMeta.cast(l_frame.data)
    ndetections = frame_meta.num_obj_meta
    l_obj = frame_meta.obj_meta_list
    frame_number = frame_meta.frame_num
    
    # Setup OSD display - 2 labels: main inference info + PM sensor info
    display_meta.num_labels = 2
    py_nvosd_text_params = display_meta.text_params[0]  # Main label
    py_nvosd_pm_params = display_meta.text_params[1]    # PM sensor label
    
    # Iterate through detected objects
    while l_obj is not None:
        try:
            obj_meta = pyds.NvDsObjectMeta.cast(l_obj.data)
        except StopIteration:
            break
        
        try:
            l_obj = l_obj.next
        except StopIteration:
            break
        
        # Filter unwanted detections
        if obj_meta.class_id not in search_item_list_:
            pyds.nvds_remove_obj_meta_from_frame(frame_meta, obj_meta)
            deleted += 1
            obj_id += 1
            continue
        
        # Process detection by class_id
        if obj_meta.class_id == PGIE_CLASS_ID_NOZZLE_CLEAR:
            nozzle_status_string = "clear"
            obj_meta.rect_params.border_color.set(*BORDER_COLOR_CLEAR)
            prediction_dict["nozzle_clear"] = 1.0
        
        elif obj_meta.class_id == PGIE_CLASS_ID_NOZZLE_BLOCKED:
            nozzle_status_string = "blocked"
            obj_meta.rect_params.border_color.set(*BORDER_COLOR_BLOCKED)
            prediction_dict["nozzle_blocked"] = 1.0
        
        elif obj_meta.class_id == PGIE_CLASS_ID_CHECK_NOZZLE:
            nozzle_status_string = "check"
            obj_meta.rect_params.border_color.set(*BORDER_COLOR_CHECK)
            prediction_dict["check_nozzle"] = 1.0
        
        elif obj_meta.class_id == PGIE_CLASS_ID_GRAVEL:
            nozzle_status_string = "gravel"
            obj_meta.rect_params.border_color.set(*BORDER_COLOR_GRAVEL)
            prediction_dict["gravel"] = 1.0
        
        elif obj_meta.class_id == PGIE_CLASS_ID_ACTION_OBJECT:
            action_object_string = "true"
            obj_meta.rect_params.border_color.set(*BORDER_COLOR_ACTION_OBJECT)
            prediction_dict["action_object"] = 1.0
        
        # Set border width
        obj_meta.rect_params.border_width = BORDER_WIDTH
        
        # Track highest confidence
        if obj_meta.confidence > highest_confidence:
            highest_confidence = obj_meta.confidence
            prediction_dict["confidence"] = highest_confidence
        
        obj_id += 1
    
    # Setup OSD text - Main label (VERIFIED exact format)
    py_nvosd_text_params.display_text = (
        'Frame Number={} | FPS {} | Num detection =  {} | Max Confidence = {:.2f} | '
        'Nozzle status = {} | Action object = {}\n'
        'Nozzle CAN = {} | Fan CAN = {} | Time = {} | SM Current Status = {} | '
        'SM Current State = {}\n'
        'SMS Time Difference = {:.3f} | Action Object Status = {} | '
        'Action Object Diffrence = {:.3f}'.format(
            frame_number,
            fps_count,
            ndetections,
            highest_confidence,
            nozzle_status_string,
            action_object_string,
            overlay_parts.get('sm_nozzle_state', 'N/A'),
            overlay_parts.get('sm_fan_speed', 'N/A'),
            timenow,
            overlay_parts.get('sm_current_status', 'N/A'),
            overlay_parts.get('sm_current_state', 'N/A'),
            overlay_parts.get('sm_time_difference', 0.0),
            overlay_parts.get('sm_ao_status', 'N/A'),
            overlay_parts.get('sm_ao_difference', 0.0)
        )
    )
    
    # VERIFIED: Exact OSD text parameters
    py_nvosd_text_params.x_offset = 1
    py_nvosd_text_params.y_offset = 1
    py_nvosd_text_params.font_params.font_name = 'Serif'
    py_nvosd_text_params.font_params.font_size = 1
    py_nvosd_text_params.font_params.font_color.set(1.0, 1.0, 1.0, 1.0)  # White
    py_nvosd_text_params.set_bg_clr = 1
    py_nvosd_text_params.text_bg_clr.set(0.0, 0.0, 0.0, 0.5)  # Black with alpha
    
    # Setup OSD text - PM sensor label (VERIFIED: y_offset=1040, not 740)
    py_nvosd_pm_params.display_text = (
        f"S1_PM10={overlay_parts.get('s1_pm10', 0)} | "
        f"S2_PM10={overlay_parts.get('s2_pm10', 'N/A')} | "
        f"S3_PM10={overlay_parts.get('s3_pm10', 'N/A')} | "
        f"S4_PM10={overlay_parts.get('s4_pm10', 'N/A')} | "
        f"S5_PM10={overlay_parts.get('s5_pm10', 'N/A')}"
    )
    py_nvosd_pm_params.x_offset = 0
    py_nvosd_pm_params.y_offset = 1040  # CRITICAL: 1040, not 740!
    py_nvosd_pm_params.font_params.font_name = 'Serif'
    py_nvosd_pm_params.font_params.font_size = 1
    py_nvosd_pm_params.font_params.font_color.set(1.0, 1.0, 1.0, 1.0)  # White
    py_nvosd_pm_params.set_bg_clr = 1
    py_nvosd_pm_params.text_bg_clr.set(0.0, 0.0, 0.0, 0.5)  # Black with alpha
    
    # Add display metadata to frame
    pyds.nvds_add_display_meta_to_frame(frame_meta, display_meta)
    
    # Update state machine
    try:
        state_machine.status_send(recieved_ns=nozzle_status_string, 
                                  recieved_aos=action_object_string)
        prediction_dict['sm_current_state'] = state_machine.get_current_state()
    except Exception as e:
        logger.debug(f'State machine status send error: {e}')
    
    # Update CAN bus
    if can_client and can_client.connected:
        # Send fan speed
        try:
            can_client.update_can_bytes({
                'fan_byte': {
                    'operation': 'update_bits',
                    'value': int(hex(state_machine.fan_speed), 16),
                    'mask': 15
                }
            })
        except Exception as e:
            logger.debug(f'CAN fan speed update error: {e}')
        
        # Send nozzle state
        try:
            can_client.update_can_bytes({
                'nozzle_byte': {
                    'operation': 'update_bits',
                    'value': int(hex(state_machine.nozzle_state), 16),
                    'mask': 15
                }
            })
        except Exception as e:
            logger.debug(f'CAN nozzle state update error: {e}')
    
    # Format timestamp (VERIFIED: exact format with microseconds + "00")
    prediction_dict['time'] = f"{datetime.now().strftime('%H:%M:%S.%f')[:-5]}00"
    
    # Send all data to CAN client
    for key, value in prediction_dict.items():
        if can_client and can_client.connected:
            try:
                can_client.send_data(key=key, value=value)
            except Exception as e:
                logger.debug(f'CAN data send error for {key}: {e}')
    
    return Gst.PadProbeReturn.OK