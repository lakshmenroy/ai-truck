#!/usr/bin/env python3

"""
Probe functions for processing buffer metadata in a GStreamer pipeline,
that will be triggered every time a new buffer arrives at the associated pad.

These functions retrieve metadata from a GStreamer buffer.

These functions use the 'pyds' (PyBindings) API to acquire resources, 
ensuring memory remains managed by the C code. This prevents premature
release by Python's garbage collector, allowing downstream plugins
to access the data.
"""

import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
import cv2 as cv  # Ensure to import opencv before numpy otherwise GStreamer TLS Error
import numpy as np
import yaml

import gi  # GStreamer
gi.require_version("Gst", "1.0")
from gi.repository import Gst

import pyds  # Python bindings for the NVIDIA DeepStream SDK

# Ensure the script's root directory is in sys.path for proper module imports
FILE = Path(__file__).resolve()
ROOT = FILE.parents[3] # /opt/deepstream-app
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from csi.utils.csi.csi_utils import (
    create_filtering_masks,
    get_discrete_csi,
    compute_csi as np_compute_csi
)
from csi.utils.general.const import (
    ROAD_UNIQUE_ID,
    GARBAGE_UNIQUE_ID
)

# === CSI settings ===
# Read the parameter configuration file
with open(file=ROOT / Path("/mnt/ssd/csi_pipeline/config/csi_config.yaml"), mode="r") as f:
    csi_config = SimpleNamespace(**yaml.safe_load(stream=f))
    csi_config.road_model = SimpleNamespace(**csi_config.road_model)  # type: ignore[arg-type]
    csi_config.garbage_model = SimpleNamespace(**csi_config.garbage_model)  # type: ignore[arg-type]
trapezoid_masks = {
    k: v for k, v in zip(["front", "rear"], create_filtering_masks(csi_config=csi_config))
}
road_class_ids = csi_config.road_model.class_ids
garbage_class_ids = csi_config.garbage_model.class_ids
n_bins = csi_config.n_bins
linsp_start = csi_config.linsp_start
linsp_stop = csi_config.linsp_stop
percentage_dirty_road = csi_config.percentage_dirty_road
garbage_type_coeffs = csi_config.garbage_type_coefficients
smooth = csi_config.smooth
clip_csi = csi_config.clip_csi
disc_levels = {
    "front": np.linspace(start=0.0, stop=1.0, num=21),
    "rear": np.linspace(start=0.0, stop=1.0, num=5)
}


def debug_input_streams_buffer_probe(pad: Gst.Pad, 
                                     info: Gst.PadProbeInfo, 
                                     u_data: int) -> Gst.PadProbeReturn:
    """
    This probe function is attached to a DeepStream pipeline to monitor and log 
    metadata from input streams. It captures details such as the frame number, 
    presentation timestamp (PTS), and other relevant stream information, 
    allowing for real-time inspection, debugging, and analysis of the video 
    frames as they pass through the pipeline.

    :param pad: The GStreamer pad to which the probe is attached.
    :param info: Probe information containing the buffer.
    :param u_data: User data passed to the probe function.

    :return: `Gst.PadProbeReturn.OK` to allow normal buffer processing.
    """
    # Retrieve the GStreamer buffer
    gst_buffer = info.get_buffer()
    if not gst_buffer:
        sys.stderr.write(" Unable to get GstBuffer\n")
        logging.error(msg="Unable to get GstBuffer\n")
        return

    # Retrieve (NvDsBatchMeta) from the gst_buffer using the
    # C address of gst_buffer as input, which is obtained with hash
    batch_meta = pyds.gst_buffer_get_nvds_batch_meta(hash(gst_buffer))
    if not batch_meta:
        return Gst.PadProbeReturn.OK

    # Retrieve the list of frames in the batch
    l_frame = batch_meta.frame_meta_list
    while l_frame is not None:
        try:
            # Retrieve (NvDsFrameMeta) using cast operation
            # Casting retains memory ownership in C,
            # preventing Python's garbage collector from interfering
            frame_meta = pyds.NvDsFrameMeta.cast(l_frame.data)
        except StopIteration:
            break
        
        key = "front" if frame_meta.pad_index == 0 else "rear"
        dt = datetime.fromtimestamp(frame_meta.ntp_timestamp / 1e9).strftime("%Y-%m-%d %H:%M:%S.%f")
        logging.info(msg=f"[INPUT] #Stream: {frame_meta.pad_index}, #Direction: {key}, #Frame: {frame_meta.frame_num}, "
                         f"Timestamp: {dt}, PTS: {frame_meta.buf_pts}")

        # # Getting Image data using nvbufsurface, the input should be address of buffer and batch_id
        # n_frame = pyds.get_nvds_buf_surface(hash(gst_buffer), frame_meta.batch_id)
        # # Convert python array into numpy array format in the copy mode.
        # frame_copy = np.array(n_frame, copy=True, order="C")
        # img_path = f"./stream_{frame_meta.pad_index}_frame_{frame_number}.png"
        # frame_copy = cv.cvtColor(frame_copy, cv.COLOR_RGB2BGR)
        # cv.imwrite(img_path, frame_copy)
        # platform_info = u_data
        # if platform_info.is_integrated_gpu():
        #     # If Jetson, since the buffer is mapped to CPU for retrieval, it must also be unmapped
        #     # The unmap call should be made after operations with the original array are complete
        #     #  The original array cannot be accessed after this call
        #     pyds.unmap_nvds_buf_surface(hash(gst_buffer), frame_meta.batch_id)

        try:
            # Moves to the next node in the NvDsFrameMeta linked list
            l_frame = l_frame.next
        except StopIteration:
            break

    return Gst.PadProbeReturn.OK


def debug_engine_outputs_buffer_probe(pad: Gst.Pad,  
                                      info: Gst.PadProbeInfo, 
                                      u_data: Any) -> Gst.PadProbeReturn:
    """
    This probe function is attached to a DeepStream pipeline to monitor and log 
    metadata related to segmentation engines. It captures frame-level information, 
    including the frame number and unique identifiers of the associated inference results,
    enabling detailed debugging and analysis of the segmentation outputs in real time.

    :param pad: The GStreamer pad to which the probe is attached.
    :param info: Probe information containing the buffer.
    :param u_data: User data passed to the probe function.

    :return: `Gst.PadProbeReturn.OK` to allow normal buffer processing.
    """
    # Retrieve the GStreamer buffer
    gst_buffer = info.get_buffer()
    if not gst_buffer:
        sys.stderr.write(" Unable to get GstBuffer\n")
        logging.error(msg="Unable to get GstBuffer\n")
        return

    # Retrieve (NvDsBatchMeta) from the gst_buffer using the
    # C address of gst_buffer as input, which is obtained with hash
    batch_meta = pyds.gst_buffer_get_nvds_batch_meta(hash(gst_buffer))
    if not batch_meta:
        return Gst.PadProbeReturn.OK

    # Retrieve the list of frames in the batch
    l_frame = batch_meta.frame_meta_list
    while l_frame is not None:
        try:
            # Retrieve (NvDsFrameMeta) using cast operation
            # Casting retains memory ownership in C,
            # preventing Python's garbage collector from interfering
            frame_meta = pyds.NvDsFrameMeta.cast(l_frame.data)
        except StopIteration:
            break

        # Retrieve the (frame_user_meta_list) from (NvDsFrameMeta) structure
        l_user = frame_meta.frame_user_meta_list
        while l_user is not None:
            try:
                # Retrieve the (NvDsUserMeta) structure
                # allows to retrieve (NvDsInferSegmentationMeta)
                seg_user_meta = pyds.NvDsUserMeta.cast(l_user.data)
            except StopIteration:
                break

            if seg_user_meta and seg_user_meta.base_meta.meta_type == \
                    pyds.NVDSINFER_SEGMENTATION_META:
                try:
                    # Retrieve (NvDsInferSegmentationMeta)
                    # Casting retains memory ownership in C,
                    # preventing Python's garbage collector from interfering
                    segmeta = pyds.NvDsInferSegmentationMeta.cast(seg_user_meta.user_meta_data)
                except StopIteration:
                    break
                
                key = "front" if frame_meta.pad_index == 0 else "rear"
                dt = datetime.fromtimestamp(frame_meta.ntp_timestamp / 1e9).strftime("%Y-%m-%d %H:%M:%S.%f")
                logging.info(msg=f"[OUTPUT] #Stream: {frame_meta.pad_index}, #Direction: {key}, " 
                                 f"#Frame: {frame_meta.frame_num}, "
                                 f"Timestamp: {dt}, PTS: {frame_meta.buf_pts}, "
                                 f"#Unique-gie: {segmeta.unique_id}, #Classes: {segmeta.classes}")

            try:
                l_user = l_user.next
            except StopIteration:
                break

        try:
            # Moves to the next node in the NvDsFrameMeta linked list
            l_frame = l_frame.next
        except StopIteration:
            break

    return Gst.PadProbeReturn.OK


def measure_fps_buffer_probe(pad: Gst.Pad, 
                             info: Gst.PadProbeInfo, 
                             u_data: Any) -> Gst.PadProbeReturn:
    """
    This probe function is attached to a DeepStream pipeline to monitor 
    and display the frame rate (FPS) of the video streams. It provides 
    real-time feedback on processing performance, allowing for performance 
    analysis and optimization of the pipeline.

    :param pad: The GStreamer pad to which the probe is attached.
    :param info: Probe information containing the buffer.
    :param u_data: User data passed to the probe function.

    :return: `Gst.PadProbeReturn.OK` to allow normal buffer processing.
    """
    # Retrieve the GStreamer buffer
    gst_buffer = info.get_buffer()
    if not gst_buffer:
        sys.stderr.write(" Unable to get GstBuffer\n")
        logging.error(msg="Unable to get GstBuffer\n")
        return

    # Retrieve (NvDsBatchMeta) from the gst_buffer using the
    # C address of gst_buffer as input, which is obtained with hash
    batch_meta = pyds.gst_buffer_get_nvds_batch_meta(hash(gst_buffer))
    if not batch_meta:
        return Gst.PadProbeReturn.OK
    
    # Retrieve the performance data object from user data
    perf_data = u_data
    
    # Retrieve the list of frames in the batch
    l_frame = batch_meta.frame_meta_list
    while l_frame is not None:
        try:
            # Retrieve (NvDsFrameMeta) using cast operation
            # Casting retains memory ownership in C,
            # preventing Python's garbage collector from interfering
            frame_meta = pyds.NvDsFrameMeta.cast(l_frame.data)
        except StopIteration:
            break

        # Update frame rate through this probe
        stream_index = "stream{0}".format(frame_meta.pad_index)
        perf_data.update_fps(stream_index)

        try:
            # Moves to the next node in the NvDsFrameMeta linked list
            l_frame = l_frame.next
        except StopIteration:
            break

    return Gst.PadProbeReturn.OK


def measure_latency_buffer_probe(pad: Gst.Pad, 
                                 info: Gst.PadProbeInfo, 
                                 u_data: Any) -> Gst.PadProbeReturn:
    """
    This probe function is attached to a DeepStream pipeline to measure 
    and display the latency of GStreamer components. It calculates the 
    latency for all frames in the current batch. The latency is measured 
    from the decoder input to the point where `pyds.nvds_measure_buffer_latency()` 
    is invoked (i.e., probe function is attached to).

    Note (Component latency measurement):
    The probe can be installed on either pad of a component to measure its latency.
    - Ref: https://docs.nvidia.com/metropolis/deepstream-nvaie30/sdk-api/group__ee__nvlatency__group.html#gab517a06e14c08d9f8699a8fe222da193

    Environment Variables:
    - `NVDS_ENABLE_LATENCY_MEASUREMENT=1`: Enables overall latency measurement.
    - `NVDS_ENABLE_COMPONENT_LATENCY_MEASUREMENT=1`: Enables per-component latency measurement
      (must be set alongside `NVDS_ENABLE_LATENCY_MEASUREMENT`).

    :param pad: The GStreamer pad where the probe is attached.
    :param info: Probe information containing the buffer being processed.
    :param u_data: User-defined data passed to the probe function.

    :return: `Gst.PadProbeReturn.OK` to allow normal buffer processing.
    """
    # Retrieve the GStreamer buffer
    gst_buffer = info.get_buffer()
    if not gst_buffer:
        sys.stderr.write(" Unable to get GstBuffer\n")
        logging.error(msg="Unable to get GstBuffer\n")
        return

    # Enable latency measurement via probe if environment variable is set
    num_sources_in_batch = pyds.nvds_measure_buffer_latency(hash(gst_buffer))
    if num_sources_in_batch == 0:
        sys.stderr.write(" Unable to get number of sources in GstBuffer for latency measurement\n")
        logging.error(msg="Unable to get number of sources in GstBuffer for latency measurement\n")

    return Gst.PadProbeReturn.OK

def display_masks(road_mask, garbage_mask, roi, gst_buffer, batch_id, frame_meta=None):
    try:
        if road_mask is not None or garbage_mask is not None:
            n_frame = pyds.get_nvds_buf_surface(hash(gst_buffer), batch_id)
            frame_array = np.array(n_frame, copy=True, order="C").astype(np.float32)
            
            h_frame, w_frame = frame_array.shape[0], frame_array.shape[1]
            num_channels = frame_array.shape[2]
            
            if road_mask is not None:
                road_mask_resized = cv.resize(road_mask.astype(np.uint8), 
                                            (w_frame, h_frame), 
                                            interpolation=cv.INTER_NEAREST)
                
                road_color = np.zeros((h_frame, w_frame, num_channels), dtype=np.float32)
                road_color[:, :, 1] = 255  
                alpha = 0.2
                road_mask_bool = (road_mask_resized > 0)[:, :, np.newaxis]
                frame_array = np.where(road_mask_bool, 
                                    frame_array * (1 - alpha) + road_color * alpha, 
                                    frame_array)
            
            if garbage_mask is not None:
                garbage_mask_resized = cv.resize(garbage_mask.astype(np.uint8), 
                                                (w_frame, h_frame), 
                                                interpolation=cv.INTER_NEAREST)
                
                if road_mask is not None:
                    road_area_mask = road_mask_resized > 0
                    garbage_mask_resized[~road_area_mask] = 0
                
                garbage_color = np.zeros((h_frame, w_frame, num_channels), dtype=np.float32)
                garbage_color[:, :, 0] = 255 
                alpha = 0.5
                garbage_mask_bool = (garbage_mask_resized > 0)[:, :, np.newaxis]
                frame_array = np.where(garbage_mask_bool, 
                                    frame_array * (1 - alpha) + garbage_color * alpha, 
                                    frame_array)
            
            frame_array = np.clip(frame_array, 0, 255).astype(np.uint8)
            
            if roi is not None:
                roi_resized = cv.resize(roi.astype(np.uint8), 
                                             (w_frame, h_frame), 
                                             interpolation=cv.INTER_NEAREST)
                contours, _ = cv.findContours(roi_resized, cv.RETR_EXTERNAL, cv.CHAIN_APPROX_SIMPLE)
                cv.drawContours(frame_array, contours, -1, (255, 0, 0), thickness=2)
            
            n_frame[:] = frame_array
    except Exception as e:
        print(f"Error during mask overlay: {e}")

def compute_csi_buffer_probe(pad: Gst.Pad,
                             info: Gst.PadProbeInfo,
                             u_data: Any) -> Gst.PadProbeReturn:
    """
    This probe function calculates CSI while ensuring mask/frame correspondence.
    """
    print("CSI probe activated")
    start_csi_probe_latency = time.perf_counter()

    csi_computation_times = []

    gst_buffer = info.get_buffer()
    if not gst_buffer:
        sys.stderr.write(" Unable to get GstBuffer\n")
        logging.error(msg="Unable to get GstBuffer\n")
        return

    batch_meta = pyds.gst_buffer_get_nvds_batch_meta(hash(gst_buffer))
    if not batch_meta:
        return Gst.PadProbeReturn.OK
    
    pyds.nvds_acquire_meta_lock(batch_meta)

    # NOW PROCESS FRAMES WITH KNOWN BATCH COMPOSITION
    l_frame = batch_meta.frame_meta_list
    while l_frame is not None:
        try:
            frame_meta = pyds.NvDsFrameMeta.cast(l_frame.data)
        except StopIteration:
            break

        road_mask, garbage_mask = None, None
        key = "front" if frame_meta.pad_index == 0 else "rear"
        batch_id = frame_meta.batch_id
        
        print(f"[FRAME_PROCESSING] batch_id={batch_id}, pad_index={frame_meta.pad_index}, direction={key}, frame_num={frame_meta.frame_num}")
        
        # Retrieve masks for THIS FRAME
        l_user = frame_meta.frame_user_meta_list
        while l_user is not None:
            try:
                seg_user_meta = pyds.NvDsUserMeta.cast(l_user.data)
            except StopIteration:
                break

            if seg_user_meta and seg_user_meta.base_meta.meta_type == \
                    pyds.NVDSINFER_SEGMENTATION_META:
                try:
                    segmeta = pyds.NvDsInferSegmentationMeta.cast(seg_user_meta.user_meta_data)
                except StopIteration:
                    break

                mask = pyds.get_segmentation_masks(segmeta)
                mask = np.array(object=mask, copy=True, order="C")
                if segmeta.unique_id == ROAD_UNIQUE_ID:
                    print(f"[MASK_RETRIEVED] batch_id={batch_id}, pad_index={frame_meta.pad_index} ({key}): ROAD mask, nonzero={np.count_nonzero(mask)}")
                    road_mask = mask              
                elif segmeta.unique_id == GARBAGE_UNIQUE_ID:
                    print(f"[MASK_RETRIEVED] batch_id={batch_id}, pad_index={frame_meta.pad_index} ({key}): GARBAGE mask, nonzero={np.count_nonzero(mask)}")
                    garbage_mask = mask

                display_masks(road_mask, garbage_mask, trapezoid_masks[key], gst_buffer, batch_id)

            try:
                l_user = l_user.next
            except StopIteration:
                break
                    
        # Compute the CSI with CORRECT masks for THIS frame
        start_time = time.perf_counter()
        print(f"Computing CSI for batch_id={batch_id}, pad_index={frame_meta.pad_index} ({key}), frame_num={frame_meta.frame_num}")
        relative_csi, absolute_csi = np_compute_csi(
            road_mask=road_mask,
            garbage_mask=garbage_mask,
            trapezoid_mask=trapezoid_masks[key],
            road_class_ids=road_class_ids,
            garbage_class_ids=garbage_class_ids,
            n_bins=n_bins,
            linsp_start=linsp_start,
            linsp_stop=linsp_stop,
            percentage_dirty_road=percentage_dirty_road,
            garbage_type_coeffs=garbage_type_coeffs,
            smooth=smooth,
            clip_csi=clip_csi
        )
        discrete_csi, _ = get_discrete_csi(
            levels=disc_levels[key], 
            continuous_csi=relative_csi
        )
        end_time = time.perf_counter()
        csi_computation_times.append(end_time - start_time)
        
        # Add CSI to custom NvDsUserMeta (CsiStructData)
        user_meta = pyds.nvds_acquire_user_meta_from_pool(batch_meta)

        if user_meta:
            dt = datetime.fromtimestamp(frame_meta.ntp_timestamp / 1e9).strftime("%Y-%m-%d %H:%M:%S.%f")
            logging.info(msg=f"[ADDCSIUSERMETA] #Stream: {frame_meta.pad_index}, #Direction: {key}, "
                         f"#Frame: {frame_meta.frame_num}, "
                         f"Timestamp: {dt}, PTS: {frame_meta.buf_pts}, Relative csi: {relative_csi}")
            data = pyds.alloc_csi_struct(user_meta)
            data.structId = frame_meta.frame_num
            data.relativeCsi = relative_csi
            data.absoluteCsi = absolute_csi
            data.discreteCsi = discrete_csi
            print(f"Added CSI user meta: batch_id={batch_id}, pad_index={frame_meta.pad_index} ({key}), Frame {frame_meta.frame_num}, CSI: {relative_csi}")
            user_meta.user_meta_data = data
            user_meta.base_meta.meta_type = pyds.NvDsMetaType.NVDS_CSI_META
            pyds.nvds_add_user_meta_to_frame(frame_meta, user_meta)
        else:
            logging.error(msg="Failed to acquire user meta\n")

        try:
            l_frame = l_frame.next
        except StopIteration:
            break

    pyds.nvds_release_meta_lock(batch_meta)

    end_csi_probe_latency = time.perf_counter()

    if csi_computation_times:
        print(f"Comp name = compute_csi_buffer_probe \tcomponent_latency = "
                f"{(end_csi_probe_latency - start_csi_probe_latency) * 1000:.6f}\n"
                f"\t\t\t\t\tcsi_computation_times = {np.array(object=csi_computation_times) * 1000}\n"
                f"\t\t\t\t\tmean_csi_computation_time = {np.mean(a=csi_computation_times) * 1000:.6f}\n"
                f"\t\t\t\t\tnon_csi_time = {((end_csi_probe_latency - start_csi_probe_latency) - np.sum(a=csi_computation_times)) * 1000:.6f}")

    return Gst.PadProbeReturn.OK


def debug_csi_user_meta_buffer_probe(pad: Gst.Pad, 
                                     info: Gst.PadProbeInfo, 
                                     u_data: Any) -> Gst.PadProbeReturn:
    """
    This probe function is attached to a DeepStream pipeline to 
    inspect and debug NvDsUserMeta in the DeepStream pipeline. 
    It helps in verifying that Clean Street Index (CSI) values have 
    been correctly attached to the metadata for each frame, 
    ensuring the integrity and correctness of the computed metrics.

    :param pad: The GStreamer pad to which the probe is attached.
    :param info: Probe information containing the buffer.
    :param u_data: User data passed to the probe function.

    :return: `Gst.PadProbeReturn.OK` to allow normal buffer processing.
    """
    gst_buffer = info.get_buffer()
    if not gst_buffer:
        print("Unable to get GstBuffer ")
        return
    
    # Retrieve (NvDsBatchMeta) from the gst_buffer using the
    # C address of gst_buffer as input, which is obtained with hash
    batch_meta = pyds.gst_buffer_get_nvds_batch_meta(hash(gst_buffer))
    if not batch_meta:
        return Gst.PadProbeReturn.OK

    pyds.nvds_acquire_meta_lock(batch_meta)

    l_frame = batch_meta.frame_meta_list
    while l_frame is not None:
        try:
            frame_meta = pyds.NvDsFrameMeta.cast(l_frame.data)
        except StopIteration:
            continue

        l_usr = frame_meta.frame_user_meta_list
        while l_usr is not None:
            try:
                user_meta = pyds.NvDsUserMeta.cast(l_usr.data)
            except StopIteration:
                continue

            if user_meta.base_meta.meta_type == pyds.NvDsMetaType.NVDS_CSI_META:
                csi_msg_meta = pyds.CsiDataStruct.cast(user_meta.user_meta_data)
                key = "front" if frame_meta.pad_index == 0 else "rear"
                logging.info(msg=f"[READCSIUSERMETA] #Stream: {frame_meta.pad_index}, #Direction: {key}, "
                             f"#Frame: {frame_meta.frame_num}, "
                             f"#StructId: {csi_msg_meta.structId}, "
                             f"Relative csi: {csi_msg_meta.relativeCsi}, " 
                             f"Absolute csi: {csi_msg_meta.absoluteCsi}, " 
                             f"Discrete csi: {csi_msg_meta.discreteCsi}")
            try:
                l_usr = l_usr.next
            except StopIteration:
                break

        try:
            l_frame = l_frame.next
        except StopIteration:
            break

    pyds.nvds_release_meta_lock(batch_meta)
    
    return Gst.PadProbeReturn.OK


def debug_csi_as_dataframe_buffer_probe(pad: Gst.Pad, 
                                        info: Gst.PadProbeInfo, 
                                        u_data: Any) -> Gst.PadProbeReturn:
    """
    This probe function is attached to a DeepStream pipeline to save 
    Clean Street Index (CSI) values to a CSV file for further analysis 
    or record-keeping. It requires a DataFrame containing the CSI data 
    to be passed as `u_data`, which is then written to the specified file.

    :param pad: The GStreamer pad to which the probe is attached.
    :param info: Probe information containing the buffer.
    :param u_data: User data passed to the probe function.

    :return: `Gst.PadProbeReturn.OK` to allow normal buffer processing.
    """
    df = u_data

    gst_buffer = info.get_buffer()
    if not gst_buffer:
        print("Unable to get GstBuffer ")
        return
    
    # Retrieve (NvDsBatchMeta) from the gst_buffer using the
    # C address of gst_buffer as input, which is obtained with hash
    batch_meta = pyds.gst_buffer_get_nvds_batch_meta(hash(gst_buffer))
    if not batch_meta:
        return Gst.PadProbeReturn.OK

    pyds.nvds_acquire_meta_lock(batch_meta)

    row_data = {}

    l_frame = batch_meta.frame_meta_list
    while l_frame is not None:
        try:
            frame_meta = pyds.NvDsFrameMeta.cast(l_frame.data)
        except StopIteration:
            continue

        dt = datetime.fromtimestamp(frame_meta.ntp_timestamp / 1e9).strftime("%Y-%m-%d %H:%M:%S.%f")
        row_data["time"] = dt

        l_usr = frame_meta.frame_user_meta_list
        while l_usr is not None:
            try:
                user_meta = pyds.NvDsUserMeta.cast(l_usr.data)
            except StopIteration:
                continue

            if user_meta.base_meta.meta_type == pyds.NvDsMetaType.NVDS_CSI_META:
                csi_msg_meta = pyds.CsiDataStruct.cast(user_meta.user_meta_data)
                key = "front" if frame_meta.pad_index == 0 else "rear"
                row_data[f"discrete_csi_{key}"] = csi_msg_meta.discreteCsi
                row_data[f"absolute_csi_{key}"] = csi_msg_meta.absoluteCsi
                row_data[f"relative_csi_{key}"] = csi_msg_meta.relativeCsi

            try:
                l_usr = l_usr.next
            except StopIteration:
                break

        try:
            l_frame = l_frame.next
        except StopIteration:
            break

    df.loc[len(df)] = row_data

    pyds.nvds_release_meta_lock(batch_meta)
    
    return Gst.PadProbeReturn.OK


def debug_save_preds_and_probs_buffer_probe(pad: Gst.Pad, 
                                            info: Gst.PadProbeInfo, 
                                            u_data: Any) -> Gst.PadProbeReturn:
    """
    This probe function is attached to a DeepStream pipeline to 
    save segmentation masks and prediction probabilities generated 
    by the inference engines. It requires specifying the save path, 
    the source stream paths, and a frame factor, which determines that 
    only every 'factor'-th frame is saved.

    :param pad: The GStreamer pad to which the probe is attached.
    :param info: Probe information containing the buffer.
    :param u_data: User data passed to the probe function.

    :return: `Gst.PadProbeReturn.OK` to allow normal buffer processing.
    """
    gies = {1: "road", 2: "garbage"}
    preds_save_path = u_data[0]
    stream_paths = u_data[1]
    factor = u_data[2]
    
    # Retrieve the GStreamer buffer
    gst_buffer = info.get_buffer()
    if not gst_buffer:
        sys.stderr.write(" Unable to get GstBuffer\n")
        logging.error(msg="Unable to get GstBuffer\n")
        return

    # Retrieve (NvDsBatchMeta) from the gst_buffer using the
    # C address of gst_buffer as input, which is obtained with hash
    batch_meta = pyds.gst_buffer_get_nvds_batch_meta(hash(gst_buffer))
    if not batch_meta:
        return Gst.PadProbeReturn.OK
    
    # Retrieve the list of frames in the batch
    l_frame = batch_meta.frame_meta_list
    while l_frame is not None:
        try:
            # Retrieve (NvDsFrameMeta) using cast operation
            # Casting retains memory ownership in C,
            # preventing Python's garbage collector from interfering
            frame_meta = pyds.NvDsFrameMeta.cast(l_frame.data)
        except StopIteration:
            break
        
        # Retrieve the (frame_user_meta_list) from (NvDsFrameMeta) structure
        l_user = frame_meta.frame_user_meta_list
        while l_user is not None:
            try:
                # Retrieve the (NvDsUserMeta) structure
                # allows to retrieve (NvDsInferSegmentationMeta)
                seg_user_meta = pyds.NvDsUserMeta.cast(l_user.data)
            except StopIteration:
                break

            if seg_user_meta and seg_user_meta.base_meta.meta_type == \
                    pyds.NVDSINFER_SEGMENTATION_META:
                try:
                    # Retrieve (NvDsInferSegmentationMeta)
                    # Casting retains memory ownership in C,
                    # preventing Python's garbage collector from interfering
                    segmeta = pyds.NvDsInferSegmentationMeta.cast(seg_user_meta.user_meta_data)
                except StopIteration:
                    break

                # Retrieve mask data in the numpy format from segmeta
                if frame_meta.frame_num % factor == 0:
                    class_map = pyds.get_segmentation_masks(segmeta)
                    class_map = np.array(object=class_map, copy=True, order="C")                
                    file = preds_save_path / f"{stream_paths[frame_meta.pad_index]}_{gies[segmeta.unique_id]}_{str(frame_meta.frame_num).zfill(5)}_mask.npz"
                    np.savez_compressed(file=file, arr=class_map, allow_pickle=False)

                # Retrieve probabilities data in the numpy format from segmeta
                if frame_meta.frame_num % factor == 0:
                    probabilities_map = pyds.get_segmentation_class_probabilities_map(segmeta)
                    probabilities_map = np.array(object=probabilities_map, copy=True, order="C")
                    file = preds_save_path / f"{stream_paths[frame_meta.pad_index]}_{gies[segmeta.unique_id]}_{str(frame_meta.frame_num).zfill(5)}_probs.npz"
                    np.savez_compressed(file=file, arr=probabilities_map, allow_pickle=False)

                # if frame_meta.frame_num % factor == 0 and -1 in class_map:
                #     temp = np.zeros_like(class_map)
                #     temp[class_map == -1] = 255
                #     file = preds_save_path / f"{stream_paths[frame_meta.pad_index]}_{gies[segmeta.unique_id]}_{str(frame_meta.frame_num).zfill(5)}_mask.npz"
                #     np.savez_compressed(file=file, arr=temp, allow_pickle=False)
                #     file = preds_save_path / f"{stream_paths[frame_meta.pad_index]}_{gies[segmeta.unique_id]}_{str(frame_meta.frame_num).zfill(5)}_probs.npz"
                #     np.savez_compressed(file=file, arr=probabilities_map, allow_pickle=False)
                
            try:
                l_user = l_user.next
            except StopIteration:
                break

        try:
            # Moves to the next node in the NvDsFrameMeta linked list
            l_frame = l_frame.next
        except StopIteration:
            break

    return Gst.PadProbeReturn.OK