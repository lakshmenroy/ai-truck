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
FIXED: Import statements corrected for refactored module structure
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

# Import SmartAssist core modules
from context import Config, AppContext, GETFPS
from detection_categories import DETECTION_CATEGORIES

# Pipeline modules
from pipeline.builder import build_pipeline, bus_call

# Camera modules - FIXED: Import CameraManager class
from camera.manager import CameraManager

# CAN modules - FIXED: Only import CANClient from can
from can.client import CANClient

# State Machine - FIXED: Import from models.nozzlenet
# Add models directory to Python path for import
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(CURRENT_DIR, '..', '..', 'models')
sys.path.insert(0, MODELS_DIR)
from nozzlenet.src.state_machine import SmartStateMachine

# Monitoring modules - FIXED: Use correct function names
from monitoring.threads import (
    start_fps_overlay_thread,
    start_manual_override_thread,
    start_socket_thread
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
    app_context.set_value('SSWP_RUN_MODE', os.environ.get('SSWP_RUN_MODE', 'SYSTEMD_NOTIFY_SERVICE'))
    app_context.set_value('last_notificationsent_to_systemd', '')
    
    # Create Config and AppContext objects
    config = Config()
    app_context_v2 = AppContext()
    fps = GETFPS(0)
    
    app_context.set_value('config', config)
    app_context.set_value('app_context_v2', app_context_v2)
    app_context.set_value('fps', fps)
    
    # Initialize logger
    logger = app_context_v2.logger
    logger.info('Application context initialized')
    
    return app_context


def signal_handler(sig, frame, loop, app_context):
    """
    Handle shutdown signals (SIGINT, SIGTERM)
    
    :param sig: Signal number
    :param frame: Current stack frame
    :param loop: GLib main loop
    :param app_context: Application context
    """
    logger = app_context.get_value('app_context_v2').logger
    logger.info(f'Received signal {sig}, initiating shutdown...')
    
    # Set shutdown flag
    app_context.set_value('shutdown_initiated_by_user_process', True)
    
    # Quit main loop
    loop.quit()


def initialize_cameras_wrapper(app_context):
    """
    Wrapper function to initialize cameras using CameraManager
    
    :param app_context: Application context
    :return: Initialization status (0 = success, -1 = failure)
    """
    logger = app_context.get_value('app_context_v2').logger
    
    try:
        logger.info('Initializing cameras...')
        
        # Create camera manager
        camera_manager = CameraManager(app_context)
        
        # Initialize cameras
        result = camera_manager.initialize()
        
        if result == 0:
            logger.info('Camera initialization successful')
        else:
            logger.error('Camera initialization failed')
        
        return result
        
    except Exception as e:
        logger.error(f'Error initializing cameras: {e}')
        return -1


def main():
    """
    Main entry point for SmartAssist pipeline
    
    Returns:
        int: Exit code (0 = success, 1 = error)
    """
    # Initialize GStreamer
    Gst.init(None)
    
    # Setup application context
    app_context = setup_app_context()
    logger = app_context.get_value('app_context_v2').logger
    
    logger.info('=' * 60)
    logger.info('SmartAssist Pipeline Starting')
    logger.info('=' * 60)
    
    # Load camera initialization status
    notify_systemd('STATUS=Loading camera init status...')
    init_status = load_latest_init_status('bucher-d3-camera-init', app_context)
    if init_status != 0:
        logger.warning('Failed to load camera init status, continuing anyway')
    
    # Initialize cameras
    notify_systemd('STATUS=Initializing cameras...')
    if initialize_cameras_wrapper(app_context) != 0:
        logger.error('Camera initialization failed')
        return 1
    
    # Load configuration
    notify_systemd('STATUS=Loading configuration...')
    config = Configuration()
    
    # Initialize CAN client
    notify_systemd('STATUS=Connecting to CAN server...')
    can_client = CANClient(client_name='smartassist-pipeline')
    if not can_client.connect():
        logger.error('Failed to connect to CAN server')
        return 1
    
    # Initialize state machine
    state_machine = SmartStateMachine()
    app_context.set_value('state_machine', state_machine)
    app_context.set_value('can_client', can_client)
    
    # Build GStreamer pipeline
    notify_systemd('STATUS=Building pipeline...')
    pipeline_result = build_pipeline(app_context)
    if pipeline_result != 0:
        logger.error('Failed to build pipeline')
        return 1
    
    pipeline = app_context.get_value('pipeline')
    
    # Create GLib main loop
    loop = GObject.MainLoop()
    app_context.set_value('loop', loop)
    
    # Setup signal handlers
    signal.signal(signal.SIGINT, lambda s, f: signal_handler(s, f, loop, app_context))
    signal.signal(signal.SIGTERM, lambda s, f: signal_handler(s, f, loop, app_context))
    
    # Start monitoring threads
    notify_systemd('STATUS=Starting monitoring threads...')
    
    # Start FPS overlay thread
    fps_thread = threading.Thread(
        target=start_fps_overlay_thread,
        args=(app_context,),
        daemon=True
    )
    fps_thread.start()
    
    # Start manual override thread
    override_thread = threading.Thread(
        target=start_manual_override_thread,
        args=(app_context,),
        daemon=True
    )
    override_thread.start()
    
    # Start socket server thread
    socket_thread = threading.Thread(
        target=start_socket_thread,
        args=(app_context,),
        daemon=True
    )
    socket_thread.start()
    
    # Start pipeline
    notify_systemd('STATUS=Starting pipeline...')
    logger.info('Setting pipeline to PLAYING state...')
    ret = pipeline.set_state(Gst.State.PLAYING)
    if ret == Gst.StateChangeReturn.FAILURE:
        logger.error('Unable to set pipeline to PLAYING state')
        return 1
    
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