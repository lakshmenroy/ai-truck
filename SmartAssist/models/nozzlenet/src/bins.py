"""
Nozzlenet Model Bins
GStreamer bin creation for nozzlenet inference

This module contains create_nozzlenet_inference_bin() which creates the
nozzlenet inference processing bin.

EXTRACTED FROM: SmartAssist/pipeline/src/pipeline/bins.py (inline code)
VERIFIED: Complete bin structure with all elements and properties
"""
import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst

# Import helper functions from pipeline module
try:
    from ...pipeline.elements import make_element
    from ...pipeline.linking import get_static_pad
except ImportError:
    # Fallback for testing
    def make_element(factory_name, name):
        return Gst.ElementFactory.make(factory_name, name)
    
    def get_static_pad(element, pad_name):
        return element.get_static_pad(pad_name)


def create_nozzlenet_inference_bin(app_context, config_paths_dict):
    """
    Create nozzlenet inference bin
    
    Pipeline structure:
    identity (placeholder) → nvdspreprocess → nvinfer (nozzlenet) → nvvideoconvert → capsfilter → queue
    
    The placeholder identity element allows us to link from the videomux output.
    The probe is attached to the nvinfer src pad.
    
    :param app_context: Application context with logger
    :param config_paths_dict: Dictionary with DeepStream config paths
    :return: GStreamer bin or None on failure
    
    VERIFIED: Extracted from inline code in create_bucher_inference_bin()
    """
    try:
        logger = app_context.get_value('app_context_v2').logger
    except:
        # Fallback logger
        import logging
        logger = logging.getLogger(__name__)
    
    logger.debug('Creating nozzlenet inference bin...')
    
    # Create bin
    nozzlenet_infer_bin = Gst.Bin.new('BUCHER-nozzlenet-infer-bin')
    nozzlenet_infer_bin.set_property('message-forward', True)
    
    # Create elements
    nozzlenet_infer_placeholder = make_element('identity', 'nozzlenet_infer_placeholder')
    preprocess = make_element('nvdspreprocess', 'nozzlenet_preprocess')
    pgie = make_element('nvinfer', 'nozzlenet-infer')
    nvvideo_conv_readjuster = make_element('nvvideoconvert', 'resize-back-to-fit-display')
    caps_filter_readjuster = make_element('capsfilter', 'capsfilter')
    queue_nozzlenet_post_infer = make_element('queue', 'queue_nozzlenet_post_infer')
    
    elements = [
        nozzlenet_infer_placeholder,
        preprocess,
        pgie,
        nvvideo_conv_readjuster,
        caps_filter_readjuster,
        queue_nozzlenet_post_infer
    ]
    
    # Verify all elements created
    for elem in elements:
        if not elem:
            logger.error(f"Failed to create element: {elem}")
            return None
    
    # Get config paths
    preprocess_config_file = config_paths_dict.get('preprocess', {}).get('path')
    infer_config_file = config_paths_dict.get('inference', {}).get('path')
    
    # Configure elements - VERIFIED exact properties
    if preprocess_config_file:
        preprocess.set_property('config-file', preprocess_config_file)
    
    if infer_config_file:
        pgie.set_property('config-file-path', infer_config_file)
    
    # CRITICAL: unique-id MUST be 1 for nozzlenet
    pgie.set_property('unique-id', 1)
    
    # Queue properties - VERIFIED
    queue_nozzlenet_post_infer.set_property('leaky', 2)  # downstream
    
    # Capsfilter for resizing back to display resolution
    caps_filter_readjuster.set_property('caps', 
                                        Gst.Caps.from_string('video/x-raw(memory:NVMM), width=960, height=540'))
    
    # Add elements to bin
    for element in elements:
        try:
            Gst.Bin.add(nozzlenet_infer_bin, element)
        except Exception as e:
            logger.error(f"Error adding element {element.get_name()} to nozzlenet_infer_bin: {e}")
            return None
    
    # Link elements
    if not (nozzlenet_infer_placeholder.link(preprocess) and
            preprocess.link(pgie) and
            pgie.link(nvvideo_conv_readjuster) and
            nvvideo_conv_readjuster.link(caps_filter_readjuster) and
            caps_filter_readjuster.link(queue_nozzlenet_post_infer)):
        logger.error("Failed to link elements in nozzlenet inference bin")
        return None
    
    # Add ghost pad for output
    nozzlenet_infer_bin.add_pad(Gst.GhostPad.new('src', get_static_pad(queue_nozzlenet_post_infer, 'src')))
    
    # Attach nozzlenet probe to pgie src pad
    try:
        from .probes import nozzlenet_src_pad_buffer_probe
        tracker_src_pad = get_static_pad(pgie, 'src')
        tracker_src_pad.add_probe(Gst.PadProbeType.BUFFER,
                                  lambda pad, info, u_data: nozzlenet_src_pad_buffer_probe(pad, info, u_data),
                                  0)
        logger.debug('Nozzlenet probe attached to pgie src pad')
    except ImportError as e:
        logger.error(f'Cannot import nozzlenet probe - inference will not work! Error: {e}')
        return None
    
    logger.debug('Nozzlenet inference bin created successfully')
    return nozzlenet_infer_bin


def get_nozzlenet_config_defaults():
    """
    Get default configuration values for nozzlenet inference
    
    :return: Dictionary with default nozzlenet config
    
    These are the expected config file paths and settings
    """
    return {
        'preprocess_config': '/mnt/ssd/csi_pipeline/config/ds_config/config_preprocess.txt',
        'inference_config': '/mnt/ssd/csi_pipeline/config/ds_config/infer_config.txt',
        'unique_id': 1,
        'output_resolution': (960, 540),
        'network_input_shape': '1;3;480;480',
        'infer_dims': '3;480;480',
        'roi_params': '230;100;960;960'
    }


def get_nozzlenet_cameras():
    """
    Get the list of camera names that use nozzlenet inference
    
    :return: List of camera names
    
    VERIFIED: These are the cameras that go through nozzlenet
    """
    return ['right', 'left']  # primary_nozzle, secondary_nozzle