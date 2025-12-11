"""
GStreamer Bin Creation
Complex bins for inference, CSI, UDP streaming, and file output

VERIFIED: Exact functionality from original pipeline_w_logging.py
This is a CRITICAL file - ~600 lines of bin creation logic
"""
import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst
import sys
from datetime import datetime

from .elements import make_element
from .linking import (
    link_request_srcpad_to_static_sinkpad,
    link_static_srcpad_pad_to_request_sinkpad,
    get_static_pad,
    get_request_pad
)
from ..utils.helpers import modify_deepstream_config_files


def create_csiprobebin(app_context, flip_method):
    """
    Create CSI probe bin for Clean Street Index computation
    
    Pipeline:
    nvstreammux (road) -> queue -> road_nvinfer ->
    nvstreammux (garbage) -> queue -> garbage_nvinfer ->
    nvsegvisual -> queue (with CSI probe) -> nvvideoconvert -> capsfilter -> queue
    
    :param app_context: Application context
    :param flip_method: Video flip method (0-7)
    :return: GStreamer bin or None
    
    VERIFIED: Exact logic from original
    """
    logger = app_context.get_value('app_context_v2').logger
    logger.debug('Creating CSI probe bin...')
    
    # Create bin
    csi_probe_bin = Gst.Bin.new('csi_probe_bin')
    csi_probe_bin.set_property('message-forward', True)
    
    # Get config paths
    config_paths_dict = app_context.get_value('config_paths')
    road_config_path = config_paths_dict.get('csi_road', {}).get('path')
    garbage_config_path = config_paths_dict.get('csi_garbage', {}).get('path')
    
    # Create elements for road inference
    nvstreammux_road_pgie = make_element('nvstreammux', 'nvstreammux_road_pgie')
    queue_pre_road_pgie = make_element('queue', 'queue_pre_road_pgie')
    road_nvinfer_engine = make_element('nvinfer', 'road_nvinfer_engine')
    
    # Create elements for garbage inference
    nvstreammux_garbage_pgie = make_element('nvstreammux', 'nvstreammux_garbage_pgie')
    queue_pre_garbage_pgie = make_element('queue', 'queue_pre_garbage_pgie')
    garbage_nvinfer_engine = make_element('nvinfer', 'garbage_nvinfer_engine')
    
    # Create visualization and conversion elements
    segvisual = make_element('nvsegvisual', 'nvsegvisual')
    queue_post_garbage_pgie = make_element('queue', 'queue_post_garbage_pgie')
    rgba_to_nv12_convert = make_element('nvvideoconvert', 'rgba_to_nv12_convert')
    rgba_to_nv12_capsfilter = make_element('capsfilter', 'rgba_to_nv12_capsfilter')
    output_queue = make_element('queue', 'output_queue')
    
    # Configure elements
    if road_config_path:
        road_nvinfer_engine.set_property('config-file-path', road_config_path)
    if garbage_config_path:
        garbage_nvinfer_engine.set_property('config-file-path', garbage_config_path)
    
    # Configure road muxer
    nvstreammux_road_pgie.set_property('batch-size', 2)
    nvstreammux_road_pgie.set_property('live-source', 1)
    nvstreammux_road_pgie.set_property('batched-push-timeout', 100000000)
    nvstreammux_road_pgie.set_property('width', 960)
    nvstreammux_road_pgie.set_property('height', 540)
    nvstreammux_road_pgie.set_property('sync-inputs', True)
    
    # Configure garbage muxer
    nvstreammux_garbage_pgie.set_property('batch-size', 2)
    nvstreammux_garbage_pgie.set_property('live-source', 1)
    nvstreammux_garbage_pgie.set_property('batched-push-timeout', 100000000)
    nvstreammux_garbage_pgie.set_property('width', 960)
    nvstreammux_garbage_pgie.set_property('height', 540)
    
    # Configure segvisual
    segvisual.set_property('batch-size', 2)
    segvisual.set_property('width', 960)
    segvisual.set_property('height', 540)
    
    # Configure capsfilter
    rgba_to_nv12_capsfilter.set_property('caps', 
        Gst.Caps.from_string('video/x-raw(memory:NVMM), format=(string)NV12'))
    
    # Add elements to bin
    elements = [
        nvstreammux_road_pgie, queue_pre_road_pgie, road_nvinfer_engine,
        nvstreammux_garbage_pgie, queue_pre_garbage_pgie, garbage_nvinfer_engine,
        segvisual, queue_post_garbage_pgie, rgba_to_nv12_convert,
        rgba_to_nv12_capsfilter, output_queue
    ]
    
    for element in elements:
        if not element:
            logger.error('Failed to create element in CSI bin')
            return None
        Gst.Bin.add(csi_probe_bin, element)
    
    # Add ghost pads for input (two sinks for front/rear cameras)
    csi_probe_bin.add_pad(Gst.GhostPad.new('sink_0', get_request_pad(nvstreammux_road_pgie, 'sink_0')))
    csi_probe_bin.add_pad(Gst.GhostPad.new('sink_1', get_request_pad(nvstreammux_road_pgie, 'sink_1')))
    
    # Link road inference path
    nvstreammux_road_pgie.link(queue_pre_road_pgie)
    queue_pre_road_pgie.link(road_nvinfer_engine)
    
    # Link road output to garbage muxer inputs
    link_static_srcpad_pad_to_request_sinkpad(road_nvinfer_engine, nvstreammux_garbage_pgie, sink_pad_index=0)
    
    # Link garbage inference path
    nvstreammux_garbage_pgie.link(queue_pre_garbage_pgie)
    queue_pre_garbage_pgie.link(garbage_nvinfer_engine)
    garbage_nvinfer_engine.link(segvisual)
    segvisual.link(queue_post_garbage_pgie)
    
    # Add CSI computation probe HERE (critical placement!)
    try:
        # Import probe function
        from ...models.csi.src.probes import compute_csi_buffer_probe
        queue_post_garbage_pgie_pad = get_static_pad(queue_post_garbage_pgie, 'src')
        queue_post_garbage_pgie_pad.add_probe(Gst.PadProbeType.BUFFER, compute_csi_buffer_probe, 0)
        logger.debug('CSI computation probe attached')
    except ImportError:
        logger.warning('CSI module not available, skipping CSI probe')
    
    # Continue linking
    queue_post_garbage_pgie.link(rgba_to_nv12_convert)
    rgba_to_nv12_convert.link(rgba_to_nv12_capsfilter)
    rgba_to_nv12_capsfilter.link(output_queue)
    
    # Add ghost pad for output
    csi_probe_bin.add_pad(Gst.GhostPad.new('src_0', get_static_pad(output_queue, 'src')))
    
    logger.debug('CSI probe bin created')
    return csi_probe_bin


def create_hr_output_bin(app_context):
    """
    Create high-resolution output bin for video recording
    
    Pipeline:
    queue -> nvvideoconvert -> nvmultistreamtiler -> encoder -> parser -> tee
    ├─> queue -> valve -> splitmuxsink (override recording)
    └─> queue -> splitmuxsink (continuous recording)
    
    :param app_context: Application context
    :return: GStreamer bin or None
    
    VERIFIED: Exact logic from original
    """
    logger = app_context.get_value('app_context_v2').logger
    logger.debug('Creating HR output bin...')
    
    # Get context values
    enhanced_logging = app_context.get_value('enhanced_logging')
    num_sources = app_context.get_value('num_sources')
    log_directory = app_context.get_value('log_directory')
    serial_number = app_context.get_value('serial_number')
    file_start_time = app_context.get_value('file_start_time')
    log_duration = app_context.get_value('log_duration')
    
    # Create bin
    hr_output_bin = Gst.Bin.new('hr_output_bin')
    hr_output_bin.set_property('message-forward', False)
    
    # Create elements
    queue_filesink = make_element('queue', 'queue_filesink')
    clear_convert = make_element('nvvideoconvert', 'clear_convert')
    clear_tiler = make_element('nvmultistreamtiler', 'clear_tiler')
    clear_encoder = make_element('nvv4l2h265enc', 'clear_encoder')
    clear_parser = make_element('h265parse', 'clear_parser')
    tee = make_element('tee', 'overide_tee')
    
    # Override recording path
    post_encode_queue = make_element('queue', 'post_encode_queue')
    overide_valve = make_element('valve', 'overide_valve')
    overide_splitmux = make_element('splitmuxsink', 'overide_splitmux')
    
    # Continuous recording path
    clear_queue = make_element('queue', 'clear_queue')
    clear_splitmux = make_element('splitmuxsink', 'clear_splitmux')
    
    elements = [
        queue_filesink, clear_convert, clear_tiler, clear_encoder, clear_parser,
        overide_valve, post_encode_queue, overide_splitmux, tee, clear_queue, clear_splitmux
    ]
    
    for element in elements:
        if not element:
            logger.error(f'Failed to create element in HR output bin')
            return None
    
    # Configure queue
    queue_filesink.set_property('leaky', 2)
    queue_filesink.set_property('max-size-buffers', 300)
    queue_filesink.set_property('flush-on-eos', True)
    
    # Configure tiler
    clear_tiler_rows = 2
    tiler_columns = 2
    clear_tiler_width = 3840
    clear_tiler_height = 2160
    clear_tiler.set_property('rows', clear_tiler_rows)
    clear_tiler.set_property('columns', tiler_columns)
    clear_tiler.set_property('width', clear_tiler_width)
    clear_tiler.set_property('height', clear_tiler_height)
    
    # Configure encoder
    clear_encoder.set_property('bitrate', 6000000 * num_sources)
    clear_encoder.set_property('insert-sps-pps', 1)
    clear_encoder.set_property('qos', True)
    clear_encoder.set_property('profile', 1)
    clear_encoder.set_property('iframeinterval', 10)
    
    # Configure override valve (drops frames when not in override mode)
    if not enhanced_logging:
        overide_valve.set_property('drop', True)
    
    # Configure queues
    clear_queue.set_property('leaky', 2)
    clear_queue.set_property('max-size-buffers', 30)
    clear_queue.set_property('flush-on-eos', True)
    
    post_encode_queue.set_property('leaky', 2)
    post_encode_queue.set_property('max-size-buffers', 0)
    post_encode_queue.set_property('max-size-bytes', 0)
    post_encode_queue.set_property('max-size-time', 10000000000)  # 10 seconds
    post_encode_queue.set_property('min-threshold-time', 10000000000)
    post_encode_queue.set_property('flush-on-eos', True)
    
    # Configure splitmuxsinks (20-minute chunks)
    log_duration_ns = int(f'{log_duration}000000000')
    
    # Override recording (when enhanced logging enabled)
    if not enhanced_logging:
        timestamp = datetime.now().strftime('%Y_%m_%d_%H%M')
        logfile = f'/mnt/syslogic_sd_card/upload/override@{timestamp}'
    else:
        logfile = f'{log_directory}/upload/{serial_number}_{file_start_time}'
    overide_splitmux.set_property('location', f'{logfile}_%d.h265')
    overide_splitmux.set_property('max-size-time', log_duration_ns)
    overide_splitmux.set_property('async-handling', True)
    
    # Continuous recording
    logfile = f'/mnt/syslogic_sd_card/{serial_number}_{file_start_time}'
    clear_splitmux.set_property('location', f'{logfile}_%d.h265')
    clear_splitmux.set_property('max-size-time', log_duration_ns)
    clear_splitmux.set_property('async-handling', True)
    
    # Add elements to bin
    for element in elements:
        try:
            hr_output_bin.add(element)
        except Exception as e:
            logger.error(f'Failed to add element {element.get_name()}: {e}')
            return None
    
    # Link elements
    if not (queue_filesink.link(clear_convert) and
            clear_convert.link(clear_tiler) and
            clear_tiler.link(clear_encoder) and
            clear_encoder.link(clear_parser) and
            clear_parser.link(tee) and
            post_encode_queue.link(overide_valve) and
            clear_queue.link(clear_splitmux) and
            overide_valve.link(overide_splitmux)):
        logger.error('Elements could not be linked in HR output bin')
        return None
    
    # Link tee to both paths
    link_request_srcpad_to_static_sinkpad(tee, post_encode_queue, src_pad_index=0)
    link_request_srcpad_to_static_sinkpad(tee, clear_queue, src_pad_index=1)
    
    # Add ghost pad
    sink_pad = get_static_pad(queue_filesink, 'sink')
    ghost_pad = Gst.GhostPad.new('sink', sink_pad)
    if not hr_output_bin.add_pad(ghost_pad):
        logger.error('Failed to add ghost pad to HR output bin')
        return None
    
    logger.debug('HR output bin created')
    return hr_output_bin


def create_udpsinkbin(app_context):
    """
    Create UDP sink bin for streaming
    
    Pipeline:
    queue -> nvvideoconvert -> capsfilter -> encoder -> tee
    ├─> queue -> parser -> splitmuxsink (file recording)
    └─> identity -> codecparse -> rtppay -> queue -> udpsink (UDP stream)
    
    :param app_context: Application context
    :return: GStreamer bin or None
    
    VERIFIED: Exact logic from original
    """
    logger = app_context.get_value('app_context_v2').logger
    logger.debug('Creating UDP sink bin...')
    
    # Get context values
    serial_number = app_context.get_value('serial_number')
    file_start_time = app_context.get_value('file_start_time')
    log_duration = app_context.get_value('log_duration')
    codec = 'h265'
    logfile = f"/mnt/syslogic_sd_card/{serial_number}_{file_start_time}_inference"
    
    # Create bin
    udpsinkbin = Gst.Bin.new("udpsinkbin")
    if not udpsinkbin:
        logger.error("Failed to create udpsinkbin")
        return None
    udpsinkbin.set_property("message-forward", False)
    
    # Create elements
    queue = make_element("queue", "udpsink_queue")
    nvvideoconvert = make_element("nvvideoconvert", "udpsink_videoconvert")
    capsfilter = make_element("capsfilter", "udpsink_capsfilter")
    encoder = make_element("nvv4l2h265enc", "udpsink_encoder")
    udpsink_tee = make_element("tee", "udpsink_tee")
    
    # File recording path
    udp_filesink_queue = make_element("queue", "udp_filesink_queue")
    filesink_parser = make_element("h265parse", "filesink_parser")
    udp_filesink = make_element("splitmuxsink", "udp_filesink")
    
    # UDP streaming path
    identity = make_element("identity", "identity0")
    codecparse = make_element("h265parse", "udpsink_codecparse")
    rtppay = make_element("rtph265pay", "udpsink_rtppay")
    udpsink_queue = make_element("queue", "udpsink_queue_before_sink")
    udpsink = make_element("udpsink", "udpsink_udpsink")
    
    elements = [
        queue, nvvideoconvert, capsfilter, encoder, udpsink_tee,
        udp_filesink_queue, filesink_parser, udp_filesink,
        identity, codecparse, rtppay, udpsink_queue, udpsink
    ]
    
    for element in elements:
        if not element:
            logger.error(f"Failed to create element in UDP sink bin")
            return None
    
    # Configure elements
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
    
    # Configure queues
    queue.set_property("leaky", "downstream")
    queue.set_property("flush-on-eos", True)
    queue.set_property("max-size-buffers", 1)
    udpsink_queue.set_property("leaky", "downstream")
    udpsink_queue.set_property("flush-on-eos", True)
    udpsink_queue.set_property("max-size-buffers", 30)
    udp_filesink_queue.set_property("leaky", "downstream")
    udp_filesink_queue.set_property("flush-on-eos", True)
    udp_filesink_queue.set_property("max-size-buffers", 30)
    
    # Configure splitmuxsink
    udp_filesink.set_property("max-size-time", int(f'{log_duration}000000000'))
    udp_filesink.set_property('async-handling', True)
    udp_filesink.set_property('location', f'{logfile}_%d.{codec}')
    
    # Add elements to bin
    for element in elements:
        udpsinkbin.add(element)
    
    # Link elements
    if not (queue.link(nvvideoconvert) and
            nvvideoconvert.link(capsfilter) and
            capsfilter.link(encoder) and
            encoder.link(udpsink_tee) and
            udp_filesink_queue.link(filesink_parser) and
            filesink_parser.link(udp_filesink) and
            identity.link(codecparse) and
            codecparse.link(rtppay) and
            rtppay.link(udpsink_queue) and
            udpsink_queue.link(udpsink)):
        logger.error("Elements could not be linked in UDP sink bin")
        return None
    
    # Link tee to both paths
    link_request_srcpad_to_static_sinkpad(udpsink_tee, udp_filesink_queue, src_pad_index=0)
    link_request_srcpad_to_static_sinkpad(udpsink_tee, identity, src_pad_index=1)
    
    # Add ghost pad
    sink_pad = get_static_pad(queue, "sink")
    ghost_pad = Gst.GhostPad.new("sink", sink_pad)
    if not udpsinkbin.add_pad(ghost_pad):
        logger.error("Failed to add ghost pad to udpsinkbin")
        return None
    
    logger.debug('UDP sink bin created')
    return udpsinkbin


def create_bucher_inference_bin(app_context):
    """
    Create the main inference bin - THIS IS THE HEART OF THE PIPELINE
    
    Structure:
    tee (splits input 3 ways):
    ├─> HR output bin (high-res recording)
    ├─> streamdemuxer -> per-camera processing:
    │   ├─> nozzle cameras -> videomux -> nozzlenet inference
    │   └─> CSI cameras -> csi_merger -> CSI probe bin
    └─> metamux (combines all metadata) -> output
    
    :param app_context: Application context
    :return: 0 on success, 1 on failure
    
    """
    logger = app_context.get_value('app_context_v2').logger
    logger.debug('Creating inference bin...')
    
    # Get configuration
    config_paths_dict_ = app_context.get_value('config_paths')
    cameras = app_context.get_value('init_config')['cameras']
    
    # Modify DeepStream config files at runtime
    preprocess_config_file_path = config_paths_dict_.get('preprocess', {})['path']
    preprocess_config_draw_roi = config_paths_dict_.get('preprocess', {})['draw-roi']
    preprocess_config_roi_params_src_0 = config_paths_dict_.get('preprocess', {})['roi-params-src-0']
    preprocess_config_network_input_shape = config_paths_dict_.get('preprocess', {})['network-input-shape']
    
    infer_config_file_path = config_paths_dict_.get('inference', {})['path']
    infer_config_model_engine_file = config_paths_dict_.get('inference', {})['model-engine-file']
    infer_config_labelfile_path = config_paths_dict_.get('inference', {})['labelfile-path']
    infer_config_input_tensor_from_meta = config_paths_dict_.get('inference', {})['input-tensor-from-meta']
    infer_config_infer_dims = config_paths_dict_.get('inference', {})['infer-dims']
    
    modify_deepstream_config_files(preprocess_config_file_path, preprocess_config_file_path, 'group-0', 'draw-roi', preprocess_config_draw_roi, app_context)
    modify_deepstream_config_files(preprocess_config_file_path, preprocess_config_file_path, 'group-0', 'roi-params-src-0', preprocess_config_roi_params_src_0, app_context)
    modify_deepstream_config_files(preprocess_config_file_path, preprocess_config_file_path, 'property', 'network-input-shape', preprocess_config_network_input_shape, app_context)
    modify_deepstream_config_files(infer_config_file_path, infer_config_file_path, 'property', 'model-engine-file', infer_config_model_engine_file, app_context)
    modify_deepstream_config_files(infer_config_file_path, infer_config_file_path, 'property', 'labelfile-path', infer_config_labelfile_path, app_context)
    modify_deepstream_config_files(infer_config_file_path, infer_config_file_path, 'property', 'input-tensor-from-meta', infer_config_input_tensor_from_meta, app_context)
    modify_deepstream_config_files(infer_config_file_path, infer_config_file_path, 'property', 'infer-dims', infer_config_infer_dims, app_context)
    
    metamux_config_file_path = config_paths_dict_.get('metamux', {})['path']
    num_sources = len([camera for camera in cameras if camera.get('capture_test_passed') == True])
    app_context.set_value('num_sources', num_sources)
    
    # Create parent inference bin
    inference_bin = Gst.Bin.new('bucher_inference_bin')
    if not inference_bin:
        logger.error('Failed to create parent bucher_inference_bin')
        return 1
    inference_bin.set_property('message-forward', True)
    
    # Create input tee (splits stream 3 ways)
    inference_bin_tee = make_element('tee', 'inference_bin_tee')
    Gst.Bin.add(inference_bin, inference_bin_tee)
    inference_bin.add_pad(Gst.GhostPad.new('sink', get_static_pad(inference_bin_tee, 'sink')))
    
    # Create metamux for combining metadata
    metamux = make_element('nvdsmetamux', 'inference_bin_metamux')
    metamux.set_property('config-file', metamux_config_file_path)
    
    # Create videomux for combining video streams
    videomux = make_element('nvstreammux', 'videomux')
    videomux.set_property('batch-size', num_sources)
    videomux.set_property('live-source', 1)
    videomux.set_property('batched-push-timeout', 33000000)
    videomux.set_property('width', 960)
    videomux.set_property('height', 540)
    
    Gst.Bin.add(inference_bin, videomux)
    Gst.Bin.add(inference_bin, metamux)
    inference_bin.add_pad(Gst.GhostPad.new('src', get_static_pad(metamux, 'src')))
    
    # Create HR output bin (branch 1)
    queue_to_stream_demuxer = make_element('queue', 'queue_to_streamdemuxer')
    Gst.Bin.add(inference_bin, queue_to_stream_demuxer)
    
    hr_output_bin = create_hr_output_bin(app_context)
    Gst.Bin.add(inference_bin, hr_output_bin)
    link_request_srcpad_to_static_sinkpad(inference_bin_tee, hr_output_bin, src_pad_index=0)
    
    # Create stream demuxer (branch 2)
    link_request_srcpad_to_static_sinkpad(inference_bin_tee, queue_to_stream_demuxer, src_pad_index=2)
    stream_demuxer = make_element('nvstreamdemux', 'inference_stream_demuxer')
    Gst.Bin.add(inference_bin, stream_demuxer)
    queue_to_stream_demuxer.link(stream_demuxer)
    
    # Get padmap and categorize cameras
    padmap = app_context.get_value('muxer_padmap')
    num_nozzlet_sources = 0
    num_csi_sources = 0
    nozzlenet_cameras = ['right', 'left']  # Changed from primary_nozzle, secondary_nozzle
    csi_cameras = ['front', 'rear']
    
    # Create CSI merger for front/rear cameras
    csi_merger = make_element('nvstreammux', 'csi_merger')
    csi_merger.set_property('batch-size', 2)
    csi_merger.set_property('live-source', 1)
    csi_merger.set_property('batched-push-timeout', 100000000)
    csi_merger.set_property('width', 960)
    csi_merger.set_property('height', 540)
    csi_merger.set_property('sync-inputs', True)
    Gst.Bin.add(inference_bin, csi_merger)
    
    # Process each camera
    for muxer_pad_index, camera_index in padmap.items():
        muxer_pad_index = int(muxer_pad_index)
        camera_index = int(camera_index)
        camera = cameras[camera_index]
        camera_name = camera['name']
        camera_position = camera['position']
        do_inference = camera['do_infer']
        
        logger.debug(f'Processing camera: index={camera_index}, position={camera_position}, muxer_pad={muxer_pad_index}')
        
        if camera_position in nozzlenet_cameras:
            num_nozzlet_sources += 1
            logger.debug(f'Camera {camera_name} is a nozzle view camera')
        if camera_position in csi_cameras:
            num_csi_sources += 1
            logger.debug(f'Camera {camera_name} is a street view camera')
        
        # Create per-camera queues and elements
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
        
        # Create selective streammux for this camera
        selective_streammux = make_element('nvstreammux', f'selective_streammux_{camera_name}')
        selective_streammux.set_property('batch-size', 1)
        selective_streammux.set_property('live-source', 1)
        selective_streammux.set_property('batched-push-timeout', 4000000)
        selective_streammux.set_property('width', 960)
        selective_streammux.set_property('height', 540)
        Gst.Bin.add(inference_bin, selective_streammux)
        
        # Link demuxer -> queue -> streammux -> queue -> tee
        link_request_srcpad_to_static_sinkpad(stream_demuxer, queue_to_streammux, src_pad_index=muxer_pad_index)
        link_static_srcpad_pad_to_request_sinkpad(queue_to_streammux, selective_streammux, sink_pad_index=muxer_pad_index)
        selective_streammux.link(queue_post_streammux)
        queue_post_streammux.link(tee)
        
        # Branch for nozzlenet cameras
        if camera_position in nozzlenet_cameras:
            queue_to_videomux = make_element('queue', f'queue_{camera_name}_to_videomux')
            Gst.Bin.add(inference_bin, queue_to_videomux)
            link_request_srcpad_to_static_sinkpad(tee, queue_to_videomux, src_pad_index=1)
            link_static_srcpad_pad_to_request_sinkpad(queue_to_videomux, videomux, sink_pad_index=muxer_pad_index)
        
        # Branch for CSI cameras
        if camera_position in csi_cameras:
            queue_to_inference.set_property('max-size-buffers', 1)
            queue_to_inference.set_property('leaky', 1)
            queue_to_inference.set_property('flush-on-eos', True)
            link_static_srcpad_pad_to_request_sinkpad(queue_to_inference, csi_merger, sink_pad_index=muxer_pad_index)
    
    logger.debug(f'Nozzle cameras: {num_nozzlet_sources}, CSI cameras: {num_csi_sources}')
    
    # Create nozzlenet inference bin if needed
    if num_nozzlet_sources > 0:
        logger.debug('Creating nozzlenet inference bin...')
        
        # Import nozzlenet bin creation from models
        from ...models.nozzlenet.src.bins import create_nozzlenet_inference_bin
        
        # Create the bin (probe attachment is inside this function)
        nozzlenet_infer_bin = create_nozzlenet_inference_bin(app_context, config_paths_dict_)
        
        if not nozzlenet_infer_bin:
            logger.error('Failed to create nozzlenet inference bin')
            return 1
        
        # Add nozzlenet bin to inference bin
        Gst.Bin.add(inference_bin, nozzlenet_infer_bin)
        logger.debug('Nozzlenet inference bin added to main inference bin')
        
        # Link to primary nozzle camera
        primary_inference_queue = inference_bin.get_by_name('queue_primary_nozzle_to_inference')
        if primary_inference_queue:
            primary_inference_queue.link(nozzlenet_infer_bin)
            logger.debug('Primary nozzle camera linked to nozzlenet inference bin')
        else:
            logger.warning('Primary nozzle inference queue not found')
               
    # Create CSI probe bin if needed
    if num_csi_sources > 0:
        logger.debug('Creating CSI probe bin...')
        
        flip_method = cameras[0].get('converter_flip_method', 0)
        if flip_method == 'default':
            flip_method = 0
        
        csi_probe_bin = create_csiprobebin(app_context, flip_method)
        
        if csi_probe_bin:
            # Create demuxer and rate control
            csi_demuxer = make_element('nvstreamdemux', 'csi_demuxer')
            csi_front_videorate_queue = make_element('queue', 'csi_front_videorate_queue')
            csi_rear_videorate_queue = make_element('queue', 'csi_rear_videorate_queue')
            csi_front_videomux_queue = make_element('queue', 'csi_front_videomux_queue')
            csi_rear_videomux_queue = make_element('queue', 'csi_rear_videomux_queue')
            csi_front_videorate = make_element('videorate', 'csi_front_videorate')
            csi_rear_videorate = make_element('videorate', 'csi_rear_videorate')
            
            # Get pads
            csi_bin_srcpad_0 = csi_probe_bin.get_static_pad('src_0')
            csi_demuxer_sinkpad = csi_demuxer.get_static_pad('sink')
            
            # Configure queues
            for queue in [csi_front_videomux_queue, csi_rear_videomux_queue]:
                queue.set_property('max-size-buffers', 2)
                queue.set_property('leaky', 2)
                queue.set_property('flush-on-eos', True)
            
            for queue in [csi_front_videorate_queue, csi_rear_videorate_queue]:
                queue.set_property('max-size-buffers', 2)
                queue.set_property('leaky', 2)
                queue.set_property('flush-on-eos', True)
            
            csi_front_videorate.set_property('skip-to-first', True)
            csi_rear_videorate.set_property('skip-to-first', True)
            
            # Add to bin
            Gst.Bin.add(inference_bin, csi_probe_bin)
            Gst.Bin.add(inference_bin, csi_demuxer)
            for elem in [csi_front_videorate_queue, csi_rear_videorate_queue,
                        csi_front_videomux_queue, csi_rear_videomux_queue,
                        csi_front_videorate, csi_rear_videorate]:
                Gst.Bin.add(inference_bin, elem)
            
            # Link CSI path
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
    
    # Connect videomux and nozzlenet to metamux
    link_static_srcpad_pad_to_request_sinkpad(videomux, metamux, sink_pad_index=0)
    if num_nozzlet_sources > 0:
        link_static_srcpad_pad_to_request_sinkpad(nozzlenet_infer_bin, metamux, sink_pad_index=1)
    
    app_context.set_value('bucher_inference_bin', inference_bin)
    logger.info('Inference bin created successfully')
    return 0