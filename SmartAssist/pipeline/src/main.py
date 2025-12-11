"""
SmartAssist Pipeline - Main Entry Point
Application entry point for the SmartAssist garbage detection system

This script:
1. Initializes GStreamer and loads configurations
2. Sets up camera initialization and validation
3. Creates the inference pipeline with nozzlenet and CSI models
4. Starts monitoring threads and CAN communication
5. Runs the main event loop with signal handling

EXTRACTED FROM: pipeline/pipeline_w_logging.py
MODULARIZED: Imports from organized module structure
"""
import sys
import os
import signal
import time
from datetime import datetime
import threading

# GStreamer imports
import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GObject

# Import SmartAssist modules
from context import Config, AppContext, GETFPS
from detection_categories import DETECTION_CATEGORIES

# Pipeline modules
from pipeline.builder import build_pipeline, bus_call

# Camera modules
from camera.manager import initialize_cameras

# CAN modules
from can.client import CANClient
from can.state_machine import SmartStateMachine

# Monitoring modules
from monitoring.threads import (
    overlay_parts_fetcher,
    override_monitoring,
    unix_socket_server
)

# Utils
from utils.systemd import notify_systemd, load_latest_init_status
from utils.config import Configuration
from utils.helpers import modify_deepstream_config_files

# Set up paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
os.environ['SCRIPT_EXECUTION_DIR'] = SCRIPT_DIR
os.environ['GST_DEBUG_DUMP_DOT_DIR'] = '/mnt/syslogic_sd_card'


def setup_app_context():
    """
    Initialize application context with all required values
    
    Returns:
        Gst.Structure: Application context
    """
    # Create GStreamer Structure for app context
    app_context = Gst.Structure.new_empty('app_context')
    
    # Set basic values
    app_context.set_value('main_process_id', os.getpid())
    app_context.set_value('shutdown_initiated_by_user_process', False)
    app_context.set_value('SSWP_RUN_MODE', os.environ.get('SSWP_RUN_MODE', 'STANDALONE'))
    
    # Load configurations
    config = Config()
    app_context_v2 = AppContext(config)
    app_context_v2.initialise_logging()
    
    app_context.set_value('app_context_v2', app_context_v2)
    app_context.set_value('init_config', config.config)
    
    logger = app_context_v2.logger
    logger.info('SmartAssist Pipeline Starting...')
    logger.info(f'Process ID: {os.getpid()}')
    logger.info(f'Run mode: {app_context.get_value("SSWP_RUN_MODE")}')
    
    # Load pipeline configuration
    import yaml
    with open('config/pipeline_config.yaml', 'r') as f:
        pipeline_config = yaml.safe_load(f)
    
    app_context.set_value('config_paths', pipeline_config.get('ds_configs', {}))
    app_context.set_value('enable_csi', pipeline_config.get('enable_csi', True))
    
    # Load logging configuration
    logging_config = Configuration()
    app_context.set_value('serial_number', logging_config.get_serial_number())
    app_context.set_value('log_duration', logging_config.get_log_duration())
    app_context.set_value('camera_columns', logging_config.get_camera_columns())
    app_context.set_value('log_directory', logging_config.get_directory())
    
    # Set file timestamps
    file_start_time = datetime.now().strftime('%Y_%m_%d_%H%M')
    app_context.set_value('file_start_time', file_start_time)
    
    # Create FPS counters
    nn_fps_counter = GETFPS(time_window=120)
    stream_fps_counter = GETFPS(time_window=120)
    app_context.set_value('nn_fps_counter', nn_fps_counter)
    app_context.set_value('stream_fps_counter', stream_fps_counter)
    
    # Initialize state machine
    state_machine = SmartStateMachine()
    app_context.set_value('state_machine', state_machine)
    
    # Detection categories for filtering
    search_item_list = [
        DETECTION_CATEGORIES.PGIE_CLASS_ID_NOZZLE_CLEAR.value,
        DETECTION_CATEGORIES.PGIE_CLASS_ID_NOZZLE_BLOCKED.value,
        DETECTION_CATEGORIES.PGIE_CLASS_ID_CHECK_NOZZLE.value,
        DETECTION_CATEGORIES.PGIE_CLASS_ID_GRAVEL.value,
        DETECTION_CATEGORIES.PGIE_CLASS_ID_ACTION_OBJECT.value
    ]
    app_context.set_value('search_item_list', search_item_list)
    
    # Overlay parts for OSD display
    overlay_parts = {
        'sm_nozzle_state': 'N/A',
        'sm_fan_speed': 'N/A',
        'sm_current_status': 'N/A',
        'sm_current_state': 'N/A',
        'sm_time_difference': 0.0,
        'sm_ao_status': 'N/A',
        'sm_ao_difference': 0.0,
        's1_pm10': 0,
        's2_pm10': 'N/A',
        's3_pm10': 'N/A',
        's4_pm10': 'N/A',
        's5_pm10': 'N/A'
    }
    app_context.set_value('overlay_parts', overlay_parts)
    
    return app_context


def setup_signal_handler(app_context, loop, ctrl_c_count):
    """
    Set up SIGINT (Ctrl+C) signal handler
    
    Args:
        app_context: Application context
        loop: GObject main loop
        ctrl_c_count: List with single element for counting Ctrl+C presses
    """
    logger = app_context.get_value('app_context_v2').logger
    
    def signal_handler(sig, frame):
        logger.info('=' * 60)
        logger.info('CTRL+C RECEIVED')
        logger.info('=' * 60)
        
        pipeline = app_context.get_value('pipeline')
        ctrl_c_count[0] += 1
        
        if ctrl_c_count[0] == 1:
            # First Ctrl+C: Graceful shutdown
            logger.info('Initiating graceful shutdown...')
            
            # Stop CAN client
            can_client = app_context.get_value('can_client')
            if can_client:
                logger.debug('Stopping CAN client...')
                can_client.stop_logging()
                can_client.disconnect()
            
            # Stop monitoring threads
            logger.debug('Stopping monitoring threads...')
            # Threads will be joined at cleanup
            
            # Generate DOT file
            timestamp = datetime.now().strftime('%Y_%m_%d_%H_%M_%S')
            logger.debug(f'Generating pipeline DOT file: python_pipeline_{timestamp}.dot')
            Gst.debug_bin_to_dot_file(pipeline, Gst.DebugGraphDetails.ALL, f'python_pipeline_{timestamp}')
            
            # Create symlink to latest
            dot_dir = os.environ.get('GST_DEBUG_DUMP_DOT_DIR', '/tmp')
            os.system(f"ln -sf {dot_dir}/python_pipeline_{timestamp}.dot {dot_dir}/python_pipeline_latest.dot")
            
            # Send EOS to pipeline
            time.sleep(0.5)
            app_context.set_value('shutdown_initiated_by_user_process', True)
            logger.info('Sending EOS event to pipeline...')
            pipeline.send_event(Gst.Event.new_eos())
            
            # Generate post-EOS DOT file
            Gst.debug_bin_to_dot_file(pipeline, Gst.DebugGraphDetails.ALL, f'python_pipeline_post_EOS_{timestamp}')
        
        elif ctrl_c_count[0] >= 2:
            # Second Ctrl+C: Force shutdown
            logger.warning('CTRL+C pressed twice - forcing immediate shutdown!')
            notify_systemd('STOPPING=1')
            
            if pipeline.set_state(Gst.State.NULL) == Gst.StateChangeReturn.FAILURE:
                logger.error('Failed to stop pipeline - killing process')
                os.kill(os.getpid(), signal.SIGKILL)
            else:
                logger.info('Pipeline stopped successfully')
                loop.quit()
    
    signal.signal(signal.SIGINT, signal_handler)


def main():
    """
    Main entry point
    """
    # Initialize GStreamer
    Gst.init(None)
    GObject.threads_init()
    
    # Set up systemd notification
    notify_systemd('STATUS=Initializing SmartAssist Pipeline')
    
    # Initialize app context
    app_context = setup_app_context()
    logger = app_context.get_value('app_context_v2').logger
    
    # Make app_context available globally for bus_call
    import __main__
    __main__.app_context = app_context
    
    # Initialize cameras
    logger.info('Initializing cameras...')
    notify_systemd('STATUS=Initializing cameras')
    
    try:
        # Load camera init status
        init_status = load_latest_init_status('camera_init_results', app_context)
        if init_status:
            logger.info(f'Loaded camera initialization status: {len(init_status.get("cameras", []))} cameras')
            app_context.set_value('init_config', init_status)
        else:
            # Run camera initialization
            from camera.manager import initialize_cameras
            init_result = initialize_cameras(app_context)
            if init_result != 0:
                logger.error('Camera initialization failed!')
                return -1
    except Exception as e:
        logger.error(f'Error during camera initialization: {e}')
        return -1
    
    # Initialize CAN client
    logger.info('Initializing CAN client...')
    try:
        can_client = CANClient()
        app_context.set_value('can_client', can_client)
    except Exception as e:
        logger.warning(f'Failed to initialize CAN client: {e}')
        logger.warning('Continuing without CAN communication')
        app_context.set_value('can_client', None)
    
    # Build pipeline
    logger.info('Building GStreamer pipeline...')
    notify_systemd('STATUS=Building pipeline')
    
    result = build_pipeline(app_context)
    if result != 0:
        logger.error('Failed to build pipeline!')
        return -1
    
    pipeline = app_context.get_value('pipeline')
    loop = app_context.get_value('main_loop')
    
    # Set up signal handler
    ctrl_c_count = [0]
    setup_signal_handler(app_context, loop, ctrl_c_count)
    
    # Start monitoring threads
    logger.info('Starting monitoring threads...')
    
    overlay_thread = threading.Thread(
        target=overlay_parts_fetcher,
        args=(app_context,),
        daemon=True
    )
    overlay_thread.start()
    app_context.set_value('overlay_thread', overlay_thread)
    
    monitoring_thread = threading.Thread(
        target=override_monitoring,
        args=(app_context,),
        daemon=True
    )
    monitoring_thread.start()
    app_context.set_value('monitoring_thread', monitoring_thread)
    
    # Start Unix socket server if in systemd mode
    if app_context.get_value('SSWP_RUN_MODE') == 'SYSTEMD_NOTIFY_SERVICE':
        logger.info('Starting Unix socket server...')
        stop_event = threading.Event()
        socket_path = '/tmp/smartassist_pipeline.sock'
        
        server_thread = threading.Thread(
            target=unix_socket_server,
            args=(socket_path, stop_event, app_context),
            daemon=True
        )
        server_thread.start()
        app_context.set_value('server_thread', server_thread)
        app_context.set_value('server_stop_event', stop_event)
    
    # Set pipeline to PLAYING
    logger.info('Starting pipeline...')
    notify_systemd('STATUS=Starting pipeline')
    
    ret = pipeline.set_state(Gst.State.PLAYING)
    if ret == Gst.StateChangeReturn.FAILURE:
        logger.error('Failed to set pipeline to PLAYING state')
        return -1
    
    # Connect CAN client
    can_client = app_context.get_value('can_client')
    if can_client:
        logger.info('Connecting to CAN bus...')
        can_client.connect()
        if can_client.connected:
            logger.info('CAN client connected - starting logging')
            can_client.start_logging()
        else:
            logger.warning('Failed to connect to CAN bus - continuing without CAN')
    
    # Notify systemd that we're ready
    notify_systemd('READY=1')
    notify_systemd('STATUS=Pipeline running')
    logger.info('=' * 60)
    logger.info('SmartAssist Pipeline is RUNNING')
    logger.info('=' * 60)
    
    # Run main loop
    try:
        loop.run()
    except Exception as e:
        logger.error(f'Error in main loop: {e}')
    
    # Cleanup
    logger.info('=' * 60)
    logger.info('CLEANUP')
    logger.info('=' * 60)
    
    notify_systemd('STATUS=Stopping...')
    notify_systemd('STOPPING=1')
    
    # Stop pipeline
    if pipeline and pipeline.get_state(Gst.CLOCK_TIME_NONE)[1] != Gst.State.NULL:
        logger.debug('Setting pipeline to NULL state...')
        pipeline.set_state(Gst.State.NULL)
    
    # Stop CAN client
    if can_client:
        logger.debug('Disconnecting CAN client...')
        can_client.stop_logging()
        can_client.disconnect()
    
    # Stop socket server
    if app_context.get_value('SSWP_RUN_MODE') == 'SYSTEMD_NOTIFY_SERVICE':
        stop_event = app_context.get_value('server_stop_event')
        if stop_event:
            stop_event.set()
    
    logger.info('SmartAssist Pipeline shutdown complete')
    return 0


if __name__ == '__main__':
    sys.exit(main())