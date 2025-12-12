"""
CSI Buffer Probes
Clean Street Index computation from road and garbage segmentation

VERIFIED: Exact functionality from pipeline/csi/utils/probes/probe_functions.py
This is imported by bins.py as: from ...models.csi.src.probes import compute_csi_buffer_probe
"""
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import cv2 as cv
import numpy as np
import yaml
import gi

gi.require_version("Gst", "1.0")
from gi.repository import Gst

try:
    import pyds
except ImportError:
    print("Warning: pyds not available")
    pyds = None

# Import CSI utilities
from .computation import (
    create_filtering_masks,
    get_discrete_csi,
    compute_csi as np_compute_csi
)
from .constants import ROAD_UNIQUE_ID, GARBAGE_UNIQUE_ID

# Get paths using smart path detection
from pipeline.utils.paths import CSI_ROOT
import os
config_path = os.path.join(CSI_ROOT, "config", "csi_config.yaml")

with open(config_path, mode="r") as f:
    csi_config = SimpleNamespace(**yaml.safe_load(stream=f))
    csi_config.road_model = SimpleNamespace(**csi_config.road_model)
    csi_config.garbage_model = SimpleNamespace(**csi_config.garbage_model)

# Create trapezoid masks - VERIFIED
trapezoid_masks = {
    k: v for k, v in zip(["front", "rear"], create_filtering_masks(csi_config=csi_config))
}

# CSI parameters - VERIFIED from csi_config.yaml
road_class_ids = csi_config.road_model.class_ids  # [0, 1]
garbage_class_ids = csi_config.garbage_model.class_ids  # [0, 1, 2]
n_bins = csi_config.n_bins  # 48
linsp_start = csi_config.linsp_start  # 0.7
linsp_stop = csi_config.linsp_stop  # 1.0
percentage_dirty_road = csi_config.percentage_dirty_road  # 0.5
garbage_type_coeffs = csi_config.garbage_type_coefficients  # [0.6, 0.7]
smooth = csi_config.smooth  # 2.0e-22
clip_csi = csi_config.clip_csi  # False

# Discrete CSI levels - VERIFIED
disc_levels = {
    "front": np.linspace(start=0.0, stop=1.0, num=21),
    "rear": np.linspace(start=0.0, stop=1.0, num=5)
}


def display_masks(road_mask, garbage_mask, roi, gst_buffer, batch_id, frame_meta=None):
    """
    Overlay segmentation masks on video frames for visualization
    
    VERIFIED against original display_masks function
    
    :param road_mask: Road segmentation mask
    :param garbage_mask: Garbage segmentation mask
    :param roi: Region of interest mask
    :param gst_buffer: GStreamer buffer
    :param batch_id: Batch ID
    :param frame_meta: Frame metadata (optional)
    """
    if not pyds:
        return
    
    try:
        if road_mask is not None or garbage_mask is not None:
            n_frame = pyds.get_nvds_buf_surface(hash(gst_buffer), batch_id)
            frame_array = np.array(n_frame, copy=True, order="C").astype(np.float32)
            
            h_frame, w_frame = frame_array.shape[0], frame_array.shape[1]
            num_channels = frame_array.shape[2]
            
            # Overlay road mask (green) - VERIFIED alpha=0.2
            if road_mask is not None:
                road_mask_resized = cv.resize(
                    road_mask.astype(np.uint8), 
                    (w_frame, h_frame), 
                    interpolation=cv.INTER_NEAREST
                )
                
                road_color = np.zeros((h_frame, w_frame, num_channels), dtype=np.float32)
                road_color[:, :, 1] = 255  # Green
                alpha = 0.2
                road_mask_bool = (road_mask_resized > 0)[:, :, np.newaxis]
                frame_array = np.where(
                    road_mask_bool, 
                    frame_array * (1 - alpha) + road_color * alpha, 
                    frame_array
                )
            
            # Overlay garbage mask (red) - VERIFIED alpha=0.5
            if garbage_mask is not None:
                garbage_mask_resized = cv.resize(
                    garbage_mask.astype(np.uint8), 
                    (w_frame, h_frame), 
                    interpolation=cv.INTER_NEAREST
                )
                
                # Only show garbage on road
                if road_mask is not None:
                    road_area_mask = road_mask_resized > 0
                    garbage_mask_resized[~road_area_mask] = 0
                
                garbage_color = np.zeros((h_frame, w_frame, num_channels), dtype=np.float32)
                garbage_color[:, :, 0] = 255  # Red
                alpha = 0.5
                garbage_mask_bool = (garbage_mask_resized > 0)[:, :, np.newaxis]
                frame_array = np.where(
                    garbage_mask_bool, 
                    frame_array * (1 - alpha) + garbage_color * alpha, 
                    frame_array
                )
            
            frame_array = np.clip(frame_array, 0, 255).astype(np.uint8)
            
            # Draw ROI contours (blue) - VERIFIED thickness=2
            if roi is not None:
                roi_resized = cv.resize(
                    roi.astype(np.uint8), 
                    (w_frame, h_frame), 
                    interpolation=cv.INTER_NEAREST
                )
                contours, _ = cv.findContours(roi_resized, cv.RETR_EXTERNAL, cv.CHAIN_APPROX_SIMPLE)
                cv.drawContours(frame_array, contours, -1, (255, 0, 0), thickness=2)
            
            # Update frame buffer
            n_frame[:] = frame_array
    except Exception as e:
        print(f"Error during mask overlay: {e}")


def compute_csi_buffer_probe(pad: Gst.Pad,
                             info: Gst.PadProbeInfo,
                             u_data: Any) -> Gst.PadProbeReturn:
    """
    Compute Clean Street Index from road and garbage segmentation masks
    
    This probe is attached to the CSI bin output and:
    1. Extracts road and garbage segmentation masks from DeepStream metadata
    2. Computes CSI using the masks and trapezoid ROI
    3. Adds CSI values to custom NvDsUserMeta for downstream use
    
    VERIFIED: Exact functionality from pipeline/csi/utils/probes/probe_functions.py
    
    :param pad: GStreamer pad
    :param info: Probe info containing buffer
    :param u_data: User data (unused in this version)
    :return: Gst.PadProbeReturn.OK
    """
    if not pyds:
        return Gst.PadProbeReturn.OK
    
    start_csi_probe_latency = time.perf_counter()
    csi_computation_times = []
    
    # Get buffer
    gst_buffer = info.get_buffer()
    if not gst_buffer:
        sys.stderr.write("Unable to get GstBuffer\n")
        return Gst.PadProbeReturn.OK
    
    # Get batch metadata
    batch_meta = pyds.gst_buffer_get_nvds_batch_meta(hash(gst_buffer))
    if not batch_meta:
        return Gst.PadProbeReturn.OK
    
    pyds.nvds_acquire_meta_lock(batch_meta)
    
    # Process each frame in batch
    l_frame = batch_meta.frame_meta_list
    while l_frame is not None:
        try:
            frame_meta = pyds.NvDsFrameMeta.cast(l_frame.data)
        except StopIteration:
            break
        
        road_mask, garbage_mask = None, None
        key = "front" if frame_meta.pad_index == 0 else "rear"
        batch_id = frame_meta.batch_id
        
        # Retrieve segmentation masks from user metadata
        l_user = frame_meta.frame_user_meta_list
        while l_user is not None:
            try:
                seg_user_meta = pyds.NvDsUserMeta.cast(l_user.data)
            except StopIteration:
                break
            
            if seg_user_meta and seg_user_meta.base_meta.meta_type == pyds.NVDSINFER_SEGMENTATION_META:
                try:
                    segmeta = pyds.NvDsInferSegmentationMeta.cast(seg_user_meta.user_meta_data)
                except StopIteration:
                    break
                
                # Extract mask array
                mask = pyds.get_segmentation_masks(segmeta)
                mask = np.array(object=mask, copy=True, order="C")
                
                # Identify road or garbage mask by unique_id - VERIFIED VALUES
                if segmeta.unique_id == ROAD_UNIQUE_ID:  # 2
                    road_mask = mask
                elif segmeta.unique_id == GARBAGE_UNIQUE_ID:  # 3
                    garbage_mask = mask
                
                # Display masks for debugging (only if debug enabled in config)
                if hasattr(csi_config, 'debug') and csi_config.debug:
                    display_masks(road_mask, garbage_mask, trapezoid_masks[key], gst_buffer, batch_id)
            
            try:
                l_user = l_user.next
            except StopIteration:
                break
        
        # Compute CSI if both masks available
        if road_mask is not None and garbage_mask is not None:
            start_time = time.perf_counter()
            
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
            
            # Add CSI to custom NvDsUserMeta
            user_meta = pyds.nvds_acquire_user_meta_from_pool(batch_meta)
            
            if user_meta:
                dt = datetime.fromtimestamp(frame_meta.ntp_timestamp / 1e9).strftime("%Y-%m-%d %H:%M:%S.%f")
                logging.info(
                    f"[CSI] Stream:{frame_meta.pad_index} ({key}), "
                    f"Frame:{frame_meta.frame_num}, "
                    f"CSI:{relative_csi:.3f}"
                )
                
                # Allocate and populate CSI struct
                data = pyds.alloc_csi_struct(user_meta)
                data.structId = frame_meta.frame_num
                data.relativeCsi = relative_csi
                data.absoluteCsi = absolute_csi
                data.discreteCsi = discrete_csi
                
                user_meta.user_meta_data = data
                user_meta.base_meta.meta_type = pyds.NvDsMetaType.NVDS_CSI_META
                pyds.nvds_add_user_meta_to_frame(frame_meta, user_meta)
            else:
                logging.error("Failed to acquire user meta for CSI")
        
        try:
            l_frame = l_frame.next
        except StopIteration:
            break
    
    pyds.nvds_release_meta_lock(batch_meta)
    
    # Log performance metrics
    end_csi_probe_latency = time.perf_counter()
    if csi_computation_times:
        total_latency = (end_csi_probe_latency - start_csi_probe_latency) * 1000
        mean_csi_time = np.mean(csi_computation_times) * 1000
        logging.debug(
            f"CSI Probe Latency: {total_latency:.2f}ms, "
            f"Mean CSI Computation: {mean_csi_time:.2f}ms"
        )
    
    return Gst.PadProbeReturn.OK