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
FIXED: All imports use proper package structure (NO sys.path hacks)
"""
import os
import signal
import time
from datetime import datetime
import threading

# GStreamer imports
import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GObject

# Import SmartAssist core modules (relative imports from pipeline.src)
from .context import Config, AppContext, GETFPS
from .detection_categories import DETECTION_CATEGORIES

# Pipeline modules
from .pipeline.builder import build_pipeline, bus_call

# Camera modules
from .camera.manager import CameraManager

# CAN modules
from .can.client import CANClient

# Monitoring modules
from .monitoring.threads import (
    start_fps_overlay_thread,
    start_manual_override_thread,
    start_socket_thread
)

# Utils
from .utils.systemd import notify_systemd, load_latest_init_status
from .utils.config import Configuration
from .utils.helpers import modify_deepstream_config_files

# FIXED: Import SmartStateMachine from proper package structure
# This assumes setup.py properly installs the models package
try:
    # Try absolute import (when installed via pip install -e .)
    from models.nozzlenet.state_machine import SmartStateMachine
except ImportError:
    # Fallback: Try relative path for development
    import sys
    from pathlib import Path
    REPO_ROOT = Path(__file__).resolve().parents[3]
    if str(REPO_ROOT / 'models') not in sys.path:
        sys.path.insert(0, str(REPO_ROOT / 'models'))
    from nozzlenet.src.state_machine import SmartStateMachine

# Set up environment
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
    app_context.set_value('last_notification_sent_to_systemd', '')
    
    # Create Config and AppContext objects
    config = Config()
    app_context_v2 = AppContext(config)
    fps = GETFPS(0)
    
    app_context.set_value('config', config)
    app_context.set_value('app_context_v2', app_context_v2)
    app_context.set_value('fps', fps)
    
    # Initialize logger
    app_context_v2.initialise_logging()
    logger = app_context_v2.logger
    logger.info('Application context initialized')
    logger.info(f'Process ID: {os.getpid()}')
    
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
        
        # Load camera initialization status from file
        result = load_latest_init_status('camera_init_results', app_context)
        
        if result == 0:
            logger.info('Camera initialization status loaded successfully')
            init_config = app_context.get_value('init_config')
            logger.debug(f'Camera config: {init_config}')
        else:
            logger.error('Failed to load camera initialization status')
            return -1
        
        return 0
        
    except Exception as e:
        logger.error(f'Error loading camera initialization: {e}')
        return -1


def main():
    """
    Main entry point for SmartAssist pipeline
    
    Returns:
        int: Exit code (0 = success, 1 = error)
    """
    # Initialize GStreamer
    Gst.init(None)
    GObject.threads_init()
    
    # Setup application context
    app_context = setup_app_context()
    logger = app_context.get_value('app_context_v2').logger
    
    logger.info('='*60)
    logger.info('SmartAssist Pipeline Starting')
    logger.info('='*60)
    
    # Notify systemd we're starting
    notify_systemd('STATUS=Initializing...', app_context)
    
    try:
        # Load camera initialization status
        logger.info('Loading camera initialization status...')
        cam_result = initialize_cameras_wrapper(app_context)
        
        if cam_result != 0:
            logger.error('Camera initialization failed')
            notify_systemd('STATUS=Camera initialization failed', app_context)
            return 1
        
        # Load configuration
        logger.info('Loading configuration...')
        config_obj = Configuration()
        app_context.set_value('configuration', config_obj)
        
        # Build pipeline
        logger.info('Building GStreamer pipeline...')
        pipeline = build_pipeline(app_context)
        
        if not pipeline:
            logger.error('Failed to create pipeline')
            notify_systemd('STATUS=Pipeline creation failed', app_context)
            return 1
        
        # Add bus watch
        bus = pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect('message', bus_call, loop, app_context)
        
        # Create main loop
        loop = GObject.MainLoop()
        
        # Register signal handlers
        signal.signal(signal.SIGINT, lambda s, f: signal_handler(s, f, loop, app_context))
        signal.signal(signal.SIGTERM, lambda s, f: signal_handler(s, f, loop, app_context))
        
        # Start monitoring threads
        logger.info('Starting monitoring threads...')
        fps_thread = start_fps_overlay_thread(app_context)
        override_thread = start_manual_override_thread(app_context)
        socket_thread = start_socket_thread(app_context)
        
        # Start CAN client (if enabled)
        can_client = None
        if app_context.get_value('config').enable_can:
            logger.info('Starting CAN client...')
            can_client = CANClient(app_context)
            can_client.start()
        
        # Start pipeline
        logger.info('Starting pipeline...')
        ret = pipeline.set_state(Gst.State.PLAYING)
        
        if ret == Gst.StateChangeReturn.FAILURE:
            logger.error('Unable to set pipeline to PLAYING state')
            notify_systemd('STATUS=Pipeline start failed', app_context)
            return 1
        
        # Notify systemd we're ready
        notify_systemd('READY=1\nSTATUS=Running', app_context)
        logger.info('Pipeline running')
        
        # Run main loop
        try:
            loop.run()
        except KeyboardInterrupt:
            logger.info('Interrupted by user')
        
        # Cleanup
        logger.info('Shutting down...')
        notify_systemd('STATUS=Shutting down...', app_context)
        
        # Stop pipeline
        pipeline.set_state(Gst.State.NULL)
        
        # Stop threads
        if fps_thread:
            fps_thread.join(timeout=2)
        if override_thread:
            override_thread.join(timeout=2)
        if socket_thread:
            socket_thread.join(timeout=2)
        
        # Stop CAN client
        if can_client:
            can_client.stop()
        
        logger.info('Shutdown complete')
        notify_systemd('STATUS=Stopped', app_context)
        
        return 0
        
    except Exception as e:
        logger.error(f'Fatal error: {e}', exc_info=True)
        notify_systemd(f'STATUS=Fatal error: {e}', app_context)
        return 1


if __name__ == '__main__':
    exit(main())