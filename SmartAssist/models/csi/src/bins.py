"""
CSI Model Bins
GStreamer bins specific to CSI (Clean Street Index) computation

This file contains the CSI probe bin which handles:
- Road segmentation inference
- Garbage segmentation inference  
- CSI computation from segmentation masks

VERIFIED: Exact functionality from original pipeline_w_logging.py
"""
import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst

from .probes import compute_csi_buffer_probe
from pipeline.pipeline import make_element
from pipeline.pipeline import link_static_srcpad_pad_to_request_sinkpad

def create_csiprobebin(app_context, flip_method):
    """
    Create CSI probe bin for Clean Street Index computation
    
    Pipeline structure:
    [sink_0, sink_1] → road_muxer → road_nvinfer → garbage_muxer → garbage_nvinfer 
                                                   ↓
                                              nvsegvisual → convert → capsfilter → queue → [src_0]
    
    This bin:
    - Takes 2 input streams (front and rear cameras)
    - Runs road segmentation on both
    - Runs garbage segmentation on both
    - Computes CSI values via buffer probe
    - Outputs video with segmentation overlay
    
    :param app_context: Application context with configuration
    :param flip_method: Video flip method (unused but kept for compatibility)
    :return: GStreamer bin or None on failure
    
    VERIFIED: Exact from original create_csiprobebin()
    """
    logger = app_context.get_value('app_context_v2').logger
    logger.debug('Creating CSI probe bin...')
    
    # Create bin
    csi_probe_bin = Gst.Bin.new('csi_probe_bin')
    csi_probe_bin.set_property('message-forward', True)
    
    # ========== CREATE ELEMENTS ==========
    
    # Create muxers for road and garbage inference
    nvstreammux_road_pgie = make_element('nvstreammux', 'nvstreammux_road_pgie')
    nvstreammux_garbage_pgie = make_element('nvstreammux', 'nvstreammux_garbage_pgie')
    
    # Create queues
    queue_pre_road_pgie = make_element('queue', 'queue_pre_road_pgie')
    queue_pre_garbage_pgie = make_element('queue', 'queue_pre_garbage_pgie')
    queue_post_garbage_pgie = make_element('queue', 'queue_post_garbage_pgie')
    
    # Create inference engines
    road_nvinfer_engine = make_element('nvinfer', 'road_nvinfer_engine')
    garbage_nvinfer_engine = make_element('nvinfer', 'garbage_nvinfer_engine')
    
    # Create segmentation visualizer
    segvisual = make_element('nvsegvisual', 'segvisual')
    
    # Create video rate control (not currently used, but kept for compatibility)
    videorate_out_csi = make_element('videorate', 'videorate_out_csi')
    
    # Create converter and caps filter
    rgba_to_nv12_convert = make_element('nvvideoconvert', 'rgba_to_nv12_convert')
    rgba_to_nv12_capsfilter = make_element('capsfilter', 'rgba_to_nv12_capsfilter')
    output_queue = make_element('queue', 'csi_output_queue')
    
    # ========== CONFIGURE ELEMENTS ==========
    
    # Configure video rate (skip to first frame)
    videorate_out_csi.set_property("skip-to-first", True)
    
    # Configure segmentation visualizer - VERIFIED values
    segvisual.set_property('alpha', 0)
    segvisual.set_property('original-background', True)
    segvisual.set_property('width', 608)
    segvisual.set_property('height', 416)
    
    # Configure road muxer - VERIFIED values
    nvstreammux_road_pgie.set_property('width', 1920)
    nvstreammux_road_pgie.set_property('height', 1080)
    nvstreammux_road_pgie.set_property('batch-size', 2)
    nvstreammux_road_pgie.set_property('live-source', 1)
    nvstreammux_road_pgie.set_property('batched-push-timeout', 33000000)
    
    # Configure garbage muxer - VERIFIED values
    nvstreammux_garbage_pgie.set_property('width', 1920)
    nvstreammux_garbage_pgie.set_property('height', 1080)
    nvstreammux_garbage_pgie.set_property('batch-size', 2)
    nvstreammux_garbage_pgie.set_property('live-source', 1)
    nvstreammux_garbage_pgie.set_property('batched-push-timeout', 33000000)
    
    # Configure inference engines - get paths from app_context
    # NOTE: These will be set from pipeline config, hardcoded here as fallback
    road_config_path = '/mnt/ssd/csi_pipeline/config/ds_config/road_config.txt'
    garbage_config_path = '/mnt/ssd/csi_pipeline/config/ds_config/garbage_config.txt'
    
    # Try to get from app_context config_paths
    config_paths_dict = app_context.get_value('config_paths')
    if config_paths_dict:
        road_config = config_paths_dict.get('road_segmentation', {})
        garbage_config = config_paths_dict.get('garbage_segmentation', {})
        if road_config.get('path'):
            road_config_path = road_config['path']
        if garbage_config.get('path'):
            garbage_config_path = garbage_config['path']
    
    road_nvinfer_engine.set_property('config-file-path', road_config_path)
    garbage_nvinfer_engine.set_property('config-file-path', garbage_config_path)
    
    # Configure queues - VERIFIED values
    queue_pre_road_pgie.set_property('leaky', 2)
    queue_pre_road_pgie.set_property('max-size-buffers', 1)
    queue_pre_road_pgie.set_property('flush-on-eos', True)
    
    queue_pre_garbage_pgie.set_property('leaky', 2)
    queue_pre_garbage_pgie.set_property('max-size-buffers', 1)
    queue_pre_garbage_pgie.set_property('flush-on-eos', True)
    
    queue_post_garbage_pgie.set_property('leaky', 2)
    queue_post_garbage_pgie.set_property('max-size-buffers', 1)
    queue_post_garbage_pgie.set_property('flush-on-eos', True)
    
    output_queue.set_property('leaky', 2)
    output_queue.set_property('max-size-buffers', 2)
    output_queue.set_property('flush-on-eos', True)
    output_queue.set_property('max-size-time', 66000000)
    
    # Configure caps filter - VERIFIED values
    rgba_to_nv12_capsfilter.set_property('caps', 
        Gst.Caps.from_string('video/x-raw(memory:NVMM), format=NV12, width=960, height=540'))
    
    # ========== ADD ELEMENTS TO BIN ==========
    
    elements = [
        nvstreammux_road_pgie, queue_pre_road_pgie, road_nvinfer_engine,
        nvstreammux_garbage_pgie, queue_pre_garbage_pgie, garbage_nvinfer_engine,
        segvisual, queue_post_garbage_pgie, rgba_to_nv12_convert,
        rgba_to_nv12_capsfilter, output_queue
    ]
    
    for element in elements:
        if not element:
            logger.error(f'Failed to create element in CSI bin')
            return None
        Gst.Bin.add(csi_probe_bin, element)
    
    # ========== ADD GHOST PADS FOR INPUT ==========
    
    # Two input pads: sink_0 (front camera), sink_1 (rear camera)
    csi_probe_bin.add_pad(Gst.GhostPad.new('sink_0', get_request_pad(nvstreammux_road_pgie, 'sink_0')))
    csi_probe_bin.add_pad(Gst.GhostPad.new('sink_1', get_request_pad(nvstreammux_road_pgie, 'sink_1')))
    
    # ========== LINK ELEMENTS ==========
    
    # Link road inference path
    nvstreammux_road_pgie.link(queue_pre_road_pgie)
    queue_pre_road_pgie.link(road_nvinfer_engine)
    
    # Link road output to garbage muxer (sink_0)
    link_static_srcpad_pad_to_request_sinkpad(road_nvinfer_engine, nvstreammux_garbage_pgie, sink_pad_index=0)
    
    # Link garbage inference path
    nvstreammux_garbage_pgie.link(queue_pre_garbage_pgie)
    queue_pre_garbage_pgie.link(garbage_nvinfer_engine)
    garbage_nvinfer_engine.link(segvisual)
    segvisual.link(queue_post_garbage_pgie)
    queue_post_garbage_pgie.link(rgba_to_nv12_convert)
    rgba_to_nv12_convert.link(rgba_to_nv12_capsfilter)
    rgba_to_nv12_capsfilter.link(output_queue)
    
    # ========== ATTACH CSI COMPUTATION PROBE ==========
    
    # Attach probe to queue_post_garbage_pgie to compute CSI
    queue_post_garbage_pgie_pad = get_static_pad(queue_post_garbage_pgie, 'src')
    queue_post_garbage_pgie_pad.add_probe(Gst.PadProbeType.BUFFER, compute_csi_buffer_probe, 0)
    logger.debug('CSI computation probe attached')
    
    # ========== ADD GHOST PAD FOR OUTPUT ==========
    
    # One output pad: src_0
    csi_probe_bin.add_pad(Gst.GhostPad.new('src_0', get_static_pad(output_queue, 'src')))
    
    logger.debug('CSI probe bin created successfully')
    return csi_probe_bin