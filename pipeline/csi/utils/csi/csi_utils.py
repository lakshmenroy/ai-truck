import logging
from types import SimpleNamespace

import cv2 as cv
import numpy as np


def find_xmin_xmax(src: np.array) -> tuple:
    """
    Find the minimum (first) and maximum (last) column indices containing non-zero values.

    :param src: Input numpy array.

    :return: A tuple containing the minimum and maximum column
        indices with at least a value different from zero.
    """
    if __debug__:
        ndim = 2
        if src.ndim != ndim:
            msg = f"Invalid ndim for src: {src.ndim}. Must be {ndim}."
            logging.error(msg=msg)
            raise ValueError(msg)

        min_rows = 1
        if src.shape[0] < min_rows:
            msg = f"Invalid number of rows in src: {src.shape[0]}. Must be > {min_rows}."
            logging.error(msg=msg)
            raise ValueError(msg)

        min_cols = 1
        if src.shape[1] < min_cols:
            msg = f"Invalid number of cols in src: {src.shape[1]}. Must be > {min_cols}."
            logging.error(msg=msg)
            raise ValueError(msg)

    # Check for non-zero values along columns
    non_zero_indices = np.any(src > 0, axis=0)  # src '!= 0'

    if np.any(non_zero_indices):
        # Get the index of the first column different from zero
        x_min = np.where(non_zero_indices)[0][0]
        # Get the index of the last column different from zero
        x_max = np.where(non_zero_indices)[0][-1]
    else:
        # If all values are zero, the road mask is empty (background only)
        msg = "Input array contains only zeros; no x_min/x_max can be determined."
        logging.error(msg=msg)
        raise ValueError(msg)

    # Handle the case of single column of pixels, no reliable CSI can be calculated
    if x_min == x_max:
        msg = f"Input array contains only one column; x_min == x_max ({x_min} == {x_max})."
        logging.error(msg=msg)
        raise ValueError(msg)

    # # Do the same thing
    # x_min = np.argmax(np.any(binary_mask[:, :] == 1, axis=0))
    # x_max = binary_mask.shape[1] - np.argmax(np.any(binary_mask[:, ::-1] == 1, axis=0)) - 1

    return x_min, x_max


def get_weight_matrix_linspace(n_rows: int,
                               n_cols: int,
                               n_bins: int,
                               linsp_start: float,
                               linsp_stop: float) -> np.array:
    """
    Generate a 2D weight matrix with a symmetric, linearly spaced pattern across the columns.

    The resulting matrix has values that gradually change from `linsp_start` to `linsp_stop`
    (in `n_bins` steps) on the left side, remain constant in the middle, and then symmetrically
    mirror back from `linsp_stop` to `linsp_start` on the right side.

    :param n_rows: Number of rows in the mask.
    :param n_cols: Number of columns in the mask.
    :param n_bins: Number of bins for the linearly spaced pattern.
    :param linsp_start: Starting value for linear spacing in the pattern.
    :param linsp_stop: Stopping value for linear spacing in the pattern.

    :return: Array representing the weight matrix.
    """
    if __debug__:
        if n_rows <= 0:
            msg = f"Invalid number of rows: {n_rows}. Must be > 0."
            logging.error(msg=msg)
            raise ValueError(msg)

        if n_cols <= 0:
            msg = f"Invalid number of cols: {n_cols}. Must be > 0."
            logging.error(msg=msg)
            raise ValueError(msg)

    linsp_min = 0.
    if linsp_start < linsp_min:  # Ensure valid values for weights
        logging.error(msg=f"Invalid value for linsp_start: {linsp_start}. "
                          f"Must be >= {linsp_min}. "
                          f"Resetting linsp_start to {linsp_min}.\n")
        linsp_start = linsp_min

    linsp_max = 1.
    if linsp_stop > linsp_max:  # Ensure valid values for weights
        logging.error(msg=f"Invalid value for linsp_stop: {linsp_stop}. "
                          f"Must be <= {linsp_max}. "
                          f"Resetting linsp_stop to {linsp_max}.\n")
        linsp_stop = linsp_max

    if linsp_start > linsp_stop:  # Ensure ascending weights
        logging.error(msg=f"Invalid range: linsp_start ({linsp_start}) "
                          f"must be smaller than linsp_stop ({linsp_stop}). "
                          f"Resetting to default min/max: "
                          f"linsp_start={linsp_min}, linsp_stop={linsp_max}.\n")
        linsp_start, linsp_stop = linsp_min, linsp_max

    n_bins_min = 2
    if n_bins < n_bins_min:  # Ensure valid number of bins (at least 2)
        logging.error(msg=f"Invalid value for n_bins: {n_bins}. "
                          f"Must be >= {n_bins_min}. "
                          f"Resetting to {n_bins}.\n")
        n_bins = n_bins_min

    n_bins_max = n_cols // 2
    if n_bins > n_bins_max:
        logging.error(msg=f"Invalid value for n_bins: {n_bins}. "
                          f"Must be <= n_cols // 2 ({n_bins_max}) (i.e, at least grouping=1). "
                          f"Reset to n_cols//2 ({n_bins_max}) which is the upper bound.\n")
        n_bins = n_bins_max

    # Calculate the grouping factor for the pattern:
    # it determines how many columns are set with the weight at the 'index' position in the 'weights' array
    # to achieve a matrix with N bins
    grouping = n_cols // (n_bins * 2)  # * 2 because half for left and half for right

    # Generate weights for the pattern using linspace
    weights = np.linspace(start=linsp_start, stop=linsp_stop, num=n_bins)

    # Initialize the weighted road mask (central region will be with all pixels to 1)
    w_road_mask = np.ones(shape=(n_rows, n_cols), dtype=np.float32)

    # Create a matrix with n_rows, with each row composed of repeated columns of weights (grouped in bins)
    matrix_weights = np.tile(A=np.repeat(weights, grouping, axis=0), reps=(n_rows, 1))

    # Determine start and stop columns for placing the weights symmetrically
    col_stop = matrix_weights.shape[1]
    col_start = n_cols - matrix_weights.shape[1]

    # Assign weights symmetrically to the left and right sides of the mask
    w_road_mask[:, :col_stop] = matrix_weights
    w_road_mask[:, col_start:] = matrix_weights[:, ::-1]

    return w_road_mask


def create_filtering_masks(csi_config: SimpleNamespace) -> tuple:
    """
    Create binary trapezoid masks for front and rear CSI calculations.

    The masks are defined by corner points from the configuration, filled with
    ones inside the trapezoid and zeros outside, and resized to the target
    output dimensions.

    :param csi_config: Configuration with image size, resize size, and trapezoid corner points.

    :return: Binary masks (front_mask, rear_mask) of shape (resize_h, resize_w).
    """
    img_h, img_w = csi_config.img_h, csi_config.img_w
    rsz_w, rsz_h = csi_config.resize_w, csi_config.resize_h

    if img_h <= 0:
        msg = f"Image height must be > 0, got {img_h}"
        logging.error(msg=msg)
        raise ValueError(msg)
    if img_w <= 0:
        msg = f"Image width must be > 0, got {img_w}"
        logging.error(msg=msg)
        raise ValueError(msg)
    if rsz_h <= 0:
        msg = f"Resize height must be > 0, got {rsz_h}"
        logging.error(msg=msg)
        raise ValueError(msg)
    if rsz_w <= 0:
        msg = f"Resize width must be > 0, got {rsz_w}"
        logging.error(msg=msg)
        raise ValueError(msg)

    front_roi_params = [
        csi_config.tp_front_top_left,
        csi_config.tp_front_top_right,
        csi_config.tp_front_bottom_right,
        csi_config.tp_front_bottom_left
    ]
    for idx, roi_point in enumerate(front_roi_params, start=1):
        x, y = roi_point
        if x < 0 or x > img_w:
            msg = f"Front ROI point {idx} x-coordinate out of bounds: {x} (valid range 0–{img_w})"
            logging.error(msg=msg)
            raise ValueError(msg)
        if y < 0 or y > img_h:
            msg = f"Front ROI point {idx} y-coordinate out of bounds: {y} (valid range 0–{img_h})"
            logging.error(msg=msg)
            raise ValueError(msg)

    rear_roi_params = [
        csi_config.tp_rear_top_left,
        csi_config.tp_rear_top_right,
        csi_config.tp_rear_bottom_right,
        csi_config.tp_rear_bottom_left
    ]
    for idx, roi_point in enumerate(rear_roi_params, start=1):
        x, y = roi_point
        if x < 0 or x > img_w:
            msg = f"Rear ROI point {idx} x-coordinate out of bounds: {x} (valid range 0–{img_w})"
            logging.error(msg=msg)
            raise ValueError(msg)
        if y < 0 or y > img_h:
            msg = f"Rear ROI point {idx} y-coordinate out of bounds: {y} (valid range 0–{img_h})"
            logging.error(msg=msg)
            raise ValueError(msg)

    road_class_label = csi_config.road_model.class_ids[-1]

    # Create trapezoid masks with ones for front CSI calculation
    roi = np.array(object=front_roi_params, dtype=np.int32)
    trap_mask_front = np.zeros(shape=(img_h, img_w), dtype=np.uint8)
    trap_mask_front = cv.fillPoly(img=trap_mask_front, pts=[roi], color=road_class_label)  # type: ignore[arg-type]
    trap_mask_front = cv.resize(src=trap_mask_front, dsize=(rsz_w, rsz_h), interpolation=cv.INTER_NEAREST)

    # Create trapezoid masks with ones for rear CSI calculation
    roi = np.array(object=rear_roi_params, dtype=np.int32)
    trap_mask_rear = np.zeros(shape=(img_h, img_w), dtype=np.uint8)
    trap_mask_rear = cv.fillPoly(img=trap_mask_rear, pts=[roi], color=road_class_label)  # type: ignore[arg-type]
    trap_mask_rear = cv.resize(src=trap_mask_rear, dsize=(rsz_w, rsz_h), interpolation=cv.INTER_NEAREST)

    if (not np.isin(np.unique(trap_mask_front), csi_config.road_model.class_ids).all() or
            not np.isin(np.unique(trap_mask_rear), csi_config.road_model.class_ids).all()):
        msg = f"Front/Rear trapezoid masks contain non-valid road pixels: {np.unique(trap_mask_rear)}"
        logging.error(msg=msg)
        raise ValueError(msg)

    return trap_mask_front, trap_mask_rear


def compute_csi(road_mask: np.array,
                garbage_mask: np.array,
                trapezoid_mask: np.ndarray,
                road_class_ids: list,
                garbage_class_ids: list,
                n_bins: int,
                linsp_start: float,
                linsp_stop: float,
                percentage_dirty_road: float,
                garbage_type_coeffs: list,
                smooth: float = 2e-22,
                clip_csi: bool = False) -> tuple:
    """
    Compute the Clean Street Index (CSI) using road model prediction and garbage model prediction.

    :param road_mask: Binary mask representing roads in the images.
    :param garbage_mask: Multiclass segmentation mask representing garbage areas in the images.
    :param trapezoid_mask: Trapezoid mask used to filter the road and garbage for CSI calculation.
    :param road_class_ids: Integer numbers from 0 to N, representing road mask classes.
    :param garbage_class_ids: Integer numbers from 0 to N, representing garbage mask classes.
    :param n_bins: Number of bins for the linearly spaced pattern (see get_weight_matrix_linspace).
    :param linsp_start: Starting value for linear spacing in the pattern (see get_weight_matrix_linspace).
    :param linsp_stop: Stopping value for linear spacing in the pattern (see get_weight_matrix_linspace).
    :param percentage_dirty_road: Parameter used to calculate the CSI, which indicates the percentage of road
        that must be considered to be completely dirty (e.g., 50% of the road is dirty --> the road is very dirty).
    :param garbage_type_coeffs: Parameters used to calculate the CSI, coefficients of different types of garbage
        (at position 0 foliage coefficient, at position 1 waste coefficient).
    :param smooth: Smooth parameter to prevent zero division errors during CSI calculation.
    :param clip_csi: Flag to enable final csi clipping in [0, 1]. Default is False.

    :return: A tuple containing the Relative Clean Street Index and the absolute Clean Street Index.
    """
    # Check for empty road mask
    if road_mask is not None:
        if not road_mask.any():
            msg = f"Mask does not contain road pixels."
            logging.error(msg=msg)
            return np.nan, np.nan
    else:
        msg = f"Mask is None."
        logging.error(msg=msg)
        return np.nan, np.nan

    if __debug__:
        if not np.isin(np.unique(road_mask), road_class_ids).all():
            msg = f"Road mask contains non-valid road pixels: {np.unique(road_mask)}"
            logging.error(msg=msg)
            raise ValueError(msg)  # return np.nan, np.nan

        if not np.isin(np.unique(garbage_mask), garbage_class_ids).all():
            msg = f"Garbage mask contains non-valid garbage pixels: {np.unique(garbage_mask)}"
            logging.error(msg=msg)
            raise ValueError(msg)  # return np.nan, np.nan

    # Filter road outside the trapezoid
    road_mask *= trapezoid_mask

    # Filtering garbage outside the street
    garbage_mask *= road_mask

    # Absolute csi calculation
    csi_absolute = np.sum(garbage_mask)

    try:
        # Find the minimum and the maximum column indices with at least a value different from zero
        x_min, x_max = find_xmin_xmax(src=road_mask)

        # Compute a weighted road mask to adjust garbage weights based on their proximity to the road surface,
        # giving lower weights to garbage near the sidewalk and higher weights to garbage at the center of the road
        weight_linspace_matrix = get_weight_matrix_linspace(
            n_rows=garbage_mask.shape[0],
            n_cols=(x_max + 1) - x_min,
            n_bins=n_bins,
            linsp_start=linsp_start,
            linsp_stop=linsp_stop
        )
    except ValueError:
        return np.nan, np.nan

    # Generate the weighted road mask to adjust garbage weights
    road_mask = road_mask.astype(np.float32)
    road_mask[:, x_min:x_max + 1] *= weight_linspace_matrix

    # Count non-zero pixels to determine the area of the weighted road polygon
    road_area = np.sum(road_mask)

    # Extract unique labels from the predicted garbage segmentation mask, excluding the background class (label 0)
    labels = np.unique(garbage_mask[garbage_mask != 0]).astype(np.int8)

    garbage_areas = [0] * len(garbage_type_coeffs)  # [foliage_areas, waste_areas]

    # Iterate over each type of garbage (foliage and waste) in the unique labels
    for label in labels:
        # Create a binary image (a sub-mask) for the specific garbage type (set pixels to 1)
        thresh = np.zeros_like(garbage_mask, dtype=np.float32)
        thresh[garbage_mask == label] = 1.

        # Compute weighted garbage of type 'label'
        weighted_garbage = road_mask * thresh

        # Compute the total area of weighted garbage of type 'label'
        garbage_areas[label - 1] = np.sum(weighted_garbage)

    # Compute the CSI with garbage coefficients, weighted garbage areas, percentage of dirty road and weighted road_area
    csi_relative = 0.
    for i in range(len(garbage_type_coeffs)):
        # Avoid zero-division errors using smooth
        csi_relative += garbage_type_coeffs[i] * (garbage_areas[i] / ((percentage_dirty_road * road_area) + smooth))
    csi_relative /= max(garbage_type_coeffs)  # normalization between 0 and 1 (if percentage_dirty_road equals 1)

    # The CSI is a value between 0 and 1 if percentage_dirty_road equals 1.
    # Otherwise, it can exceed 1, so we apply clipping to limit it within the [0, 1] range
    if clip_csi:
        csi_relative = np.clip(a=csi_relative, a_min=0., a_max=1.)

    return csi_relative, csi_absolute


def get_discrete_csi(levels: np.array,
                     continuous_csi: float) -> tuple:
    """
    Find the item in 'levels' array that has the minimum distance from a given continuous CSI value.

    :param levels: A numpy array representing the discrete csi values.
    :param continuous_csi: The continuous CSI value to compare against.

    :return: The item in 'levels' closest to the specified continuous CSI value
        and the level.
    """
    if __debug__:
        if levels.shape[0] <= 0:
            msg = f"Invalid levels provided: {levels}."
            logging.error(msg=msg)
            raise ValueError(msg)

    if np.isnan(continuous_csi):
        return np.nan, np.nan

    # Compute absolute differences
    distances = np.abs(levels - continuous_csi)

    # Find the index of the element with the smallest absolute difference
    min_index = np.argmin(distances)

    # Get the item with the minimum distance
    discrete_csi = levels[min_index]

    return discrete_csi, min_index
