#!/usr/bin/env python3
# upload csv and video to azure blob. csv has priority.

import sys
from pathlib import Path

# vendor path for bundled deps
VENDOR_DIR = Path(__file__).parent / "vendor"
if VENDOR_DIR.exists():
    sys.path.insert(0, str(VENDOR_DIR))

import json
import os
import re
import shutil
import time
import logging
import multiprocessing

from azure.storage.blob import BlobClient, ContentSettings

# logging, level from config
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(processName)s - %(message)s'
)
logger = logging.getLogger(__name__)
bloblogger = logging.getLogger("logger_name")
bloblogger.setLevel(logging.WARNING)

CONFIG_FILE = Path(os.getcwd()) / "config.json"


def load_config():
    """load config and make paths"""
    try:
        with open(CONFIG_FILE, 'r') as f:
            config = json.load(f)

        # log level
        log_level = config.get('log_level', 'INFO').upper()
        logging.getLogger().setLevel(getattr(logging, log_level, logging.INFO))

        # dirs
        config['csv_to_upload_path'] = Path(config['csv_to_upload_dir'])
        config['video_to_upload_path'] = Path(config['video_to_upload_dir'])
        config['csv_uploaded_path'] = Path(config['csv_uploaded_dir'])
        config['video_uploaded_path'] = Path(config['video_uploaded_dir'])

        return config
    except FileNotFoundError:
        logger.error(f"Configuration file not found: {CONFIG_FILE}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in configuration file: {e}")
        sys.exit(1)
    except KeyError as e:
        logger.error(f"Missing required config key: {e}")
        sys.exit(1)


def ensure_directories(config):
    """create dirs if not there"""
    directories = [
        config['csv_to_upload_path'],
        config['video_to_upload_path'],
        config['csv_uploaded_path'],
        config['video_uploaded_path']
    ]
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)


def extract_timestamp_from_filename(filename):
    """extract ISO timestamp from filename, return as string for sorting or None"""
    # match timestamp pattern: YYYY-MM-DDTHH:MM:SS.fffZ or similar
    pattern = r'(\d{4}-\d{2}-\d{2}T[\d:.]+Z)'
    match = re.search(pattern, filename)
    if match:
        return match.group(1)
    return None


def extract_timestamp_minute(filename):
    """extract timestamp truncated to minute (YYYY-MM-DDTHH:MM) from filename or None"""
    pattern = r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2})'
    match = re.search(pattern, filename)
    if match:
        return match.group(1)
    return None


def extract_data_type_from_csv(filename):
    """extract DATA_TYPE from CSV filename: [DATA_TYPE]_[VEHICLE_TYPE]_[VEHICLE_ID]_[TIMESTAMP].csv"""
    pattern = r'^([^_]+)_[^_]+_[^_]+_\d{4}-\d{2}-\d{2}T[\d:.]+Z\.csv$'
    match = re.match(pattern, filename)
    if match:
        return match.group(1)
    return None


def extract_data_type_from_video(filename):
    """extract DATA_TYPE from video filename: VIDEO_[VIDEO_TYPE]_[DATA_TYPE]_[VEHICLE_TYPE]_[VEHICLE_ID]_[TIMESTAMP].mp4"""
    pattern = r'^VIDEO_[^_]+_([^_]+)_[^_]+_[^_]+_\d{4}-\d{2}-\d{2}T[\d:.]+Z\.mp4$'
    match = re.match(pattern, filename)
    if match:
        return match.group(1)
    return None


def group_files_by_minute_and_datatype(files, data_type_extractor):
    """group files by timestamp minute, then by DATA_TYPE.
    returns dict: {minute: {data_type: [files...]}}"""
    groups = {}
    for f in files:
        minute = extract_timestamp_minute(f.name)
        data_type = data_type_extractor(f.name)
        if minute is None:
            minute = "unknown"
        if data_type is None:
            data_type = "unknown"
        if minute not in groups:
            groups[minute] = {}
        if data_type not in groups[minute]:
            groups[minute][data_type] = []
        groups[minute][data_type].append(f)
    return groups


def get_files_to_upload_parallel(files, data_type_extractor, max_processes=10):
    """get list of files to upload in parallel.
    returns one file per DATA_TYPE for files within the same minute, up to max_processes."""
    if not files:
        return []

    groups = group_files_by_minute_and_datatype(files, data_type_extractor)

    # get the oldest minute (files are already sorted by age)
    oldest_file = files[0]
    oldest_minute = extract_timestamp_minute(oldest_file.name)
    if oldest_minute is None:
        oldest_minute = "unknown"

    if oldest_minute not in groups:
        return [oldest_file]

    # get one file per DATA_TYPE for this minute
    files_to_upload = []
    for data_type, type_files in groups[oldest_minute].items():
        if type_files:
            files_to_upload.append(type_files[0])  # oldest file of this type
        if len(files_to_upload) >= max_processes:
            break

    return files_to_upload


def get_files_sorted_by_age(directory):
    """get files, oldest first based on timestamp in filename"""
    files = []
    if directory.exists():
        for f in directory.iterdir():
            if f.is_file():
                files.append(f)
    # oldest first by filename timestamp, fall back to mtime if no timestamp
    result = []
    for f in files:
        try:
            timestamp = extract_timestamp_from_filename(f.name)
            if timestamp:
                result.append((f, timestamp, 0))
            else:
                # fallback to mtime for files without timestamp in name
                mtime = f.stat().st_mtime
                result.append((f, None, mtime))
        except FileNotFoundError:
            continue
    # sort: files with timestamp first (by timestamp), then files without (by mtime)
    with_ts = [(f, ts) for f, ts, _ in result if ts is not None]
    without_ts = [(f, mt) for f, ts, mt in result if ts is None]
    with_ts.sort(key=lambda x: x[1])
    without_ts.sort(key=lambda x: x[1])
    return [f for f, _ in with_ts] + [f for f, _ in without_ts]


def get_csv_count(csv_to_upload_path):
    """how many csv waiting"""
    return len(get_files_sorted_by_age(csv_to_upload_path))


def get_video_count(video_to_upload_path):
    """how many video waiting"""
    return len(get_files_sorted_by_age(video_to_upload_path))


def parse_video_filename(filename):
    """VIDEO_[VIDEO_TYPE]_[DATA_TYPE]_[VEHICLE_TYPE]_[VEHICLE_ID]_[TIMESTAMP].mp4
    -> {video_type, vehicle_id, year, month, day} or None"""
    pattern = r'^VIDEO_([^_]+)_([^_]+)_([^_]+)_([^_]+)_(\d{4})-(\d{2})-(\d{2})T[\d:.]+Z\.mp4$'
    match = re.match(pattern, filename)

    if not match:
        return None

    return {
        'video_type': match.group(1),
        'vehicle_id': match.group(4),
        'year': match.group(5),
        'month': match.group(6),
        'day': match.group(7)
    }


def parse_csv_filename(filename):
    """[DATA_TYPE]_[VEHICLE_TYPE]_[VEHICLE_ID]_[TIMESTAMP].csv
    -> {vehicle_id, year, month, day} or None"""
    pattern = r'^([^_]+)_([^_]+)_([^_]+)_(\d{4})-(\d{2})-(\d{2})T[\d:.]+Z\.csv$'
    match = re.match(pattern, filename)

    if not match:
        return None

    return {
        'vehicle_id': match.group(3),
        'year': match.group(4),
        'month': match.group(5),
        'day': match.group(6)
    }


def upload_file_to_blob(file_path, blob_endpoint, sas_token, blob_path=None):
    """upload file to azure. blob_path is optional container prefix."""
    file_path = Path(file_path)
    file_name = file_path.name

    endpoint = blob_endpoint.rstrip('/')

    logger.info(f"Uploading {file_name} to blob storage...")

    try:
        # content type
        extension = file_path.suffix.lower()
        content_type = 'application/octet-stream'
        if extension == '.csv':
            content_type = 'text/csv'
        elif extension == '.mp4':
            content_type = 'video/mp4'

        # build blob url with optional path
        if blob_path:
            blob_url = f"{endpoint}/{blob_path}/{file_name}{sas_token}"
        else:
            blob_url = f"{endpoint}/{file_name}{sas_token}"

        blob_client = BlobClient.from_blob_url(blob_url, logger=bloblogger)

        with open(file_path, 'rb') as f:
            blob_client.upload_blob(
                f,
                overwrite=True,
                content_settings=ContentSettings(content_type=content_type)
            )

        logger.info(f"Successfully uploaded {file_name}")
        return True

    except Exception as e:
        logger.error(f"Failed to upload {file_name}: {e}")
        return False


def csv_upload_process(file_path):
    """upload one csv, exit 0 ok, 1 fail"""
    file_to_upload = Path(file_path)
    multiprocessing.current_process().name = f"csv upload ({file_to_upload.name})"

    config = load_config()
    blob_endpoint = config['blob_endpoint']
    sas_token = config['sas_token']
    csv_uploaded_path = config['csv_uploaded_path']

    if not file_to_upload.exists():
        logger.warning(f"CSV file no longer exists: {file_to_upload.name}")
        sys.exit(0)

    logger.info(f"Starting CSV upload: {file_to_upload.name}")

    metadata = parse_csv_filename(file_to_upload.name)
    if metadata:
        blob_path = f"Data/{metadata['vehicle_id']}/{metadata['year']}/{metadata['month']}/{metadata['day']}"
        logger.info(f"Blob path: {blob_path}")
    else:
        logger.warning(f"Could not parse CSV filename: {file_to_upload.name}, uploading to error/csv")
        blob_path = "error/csv"

    if upload_file_to_blob(file_to_upload, blob_endpoint, sas_token, blob_path):
        destination = csv_uploaded_path / file_to_upload.name
        shutil.move(str(file_to_upload), str(destination))
        logger.info(f"Moved {file_to_upload.name} to {destination}")
        sys.exit(0)
    else:
        logger.error(f"Failed to upload CSV file: {file_to_upload.name}")
        sys.exit(1)


def video_upload_process(file_path):
    """upload one video, exit 0 ok, 1 fail"""
    file_to_upload = Path(file_path)
    multiprocessing.current_process().name = f"video upload ({file_to_upload.name})"

    config = load_config()
    blob_endpoint = config['blob_endpoint']
    sas_token = config['sas_token']
    video_uploaded_path = config['video_uploaded_path']

    if not file_to_upload.exists():
        logger.warning(f"Video file no longer exists: {file_to_upload.name}")
        sys.exit(0)

    logger.info(f"Starting video upload: {file_to_upload.name}")

    metadata = parse_video_filename(file_to_upload.name)
    if metadata:
        blob_path = f"Video_Snippets/{metadata['vehicle_id']}/{metadata['year']}/{metadata['month']}/{metadata['day']}"
        logger.info(f"Blob path: {blob_path}")
    else:
        logger.warning(f"Could not parse video filename: {file_to_upload.name}, uploading to error/video")
        blob_path = "error/video"

    if upload_file_to_blob(file_to_upload, blob_endpoint, sas_token, blob_path):
        destination = video_uploaded_path / file_to_upload.name
        shutil.move(str(file_to_upload), str(destination))
        logger.info(f"Moved {file_to_upload.name} to {destination}")
        sys.exit(0)
    else:
        logger.error(f"Failed to upload video file: {file_to_upload.name}")
        sys.exit(1)


MAX_PROCESSES_PER_FILETYPE = 10


def cleanup_finished_processes(processes, process_type):
    """remove finished processes from list, log their exit codes"""
    still_running = []
    for proc, file_path in processes:
        if not proc.is_alive():
            proc.join()
            exit_code = proc.exitcode
            logger.info(f"{process_type} upload process finished for {Path(file_path).name} with exit code: {exit_code}")
        else:
            still_running.append((proc, file_path))
    return still_running


def get_files_being_uploaded(processes):
    """get set of file paths currently being uploaded"""
    return {file_path for _, file_path in processes}


def terminate_all_processes(processes, process_type):
    """terminate all processes in list"""
    for proc, file_path in processes:
        if proc.is_alive():
            logger.warning(f"Terminating {process_type} upload process for {Path(file_path).name}")
            proc.terminate()
    for proc, file_path in processes:
        proc.join()
    return []


def main():
    """main loop"""
    logger.info("Starting Azure Blob Storage Uploader")

    config = load_config()
    prioritize_csv_count = int(config.get('prioritize_csv_count', 10))
    max_csv_count = int(config.get('max_csv_count', 20))
    csv_to_upload_path = config['csv_to_upload_path']
    video_to_upload_path = config['video_to_upload_path']

    logger.info(f"prioritize_csv_count: {prioritize_csv_count}")
    logger.info(f"max_csv_count: {max_csv_count}")
    logger.info(f"max_processes_per_filetype: {MAX_PROCESSES_PER_FILETYPE}")
    logger.info(f"csv_to_upload_dir: {csv_to_upload_path}")
    logger.info(f"video_to_upload_dir: {video_to_upload_path}")
    logger.info(f"csv_uploaded_dir: {config['csv_uploaded_path']}")
    logger.info(f"video_uploaded_dir: {config['video_uploaded_path']}")

    ensure_directories(config)

    csv_processes = []  # list of (process, file_path)
    video_processes = []  # list of (process, file_path)

    while True:
        csv_files = get_files_sorted_by_age(csv_to_upload_path)
        video_files = get_files_sorted_by_age(video_to_upload_path)
        csv_count = len(csv_files)
        video_count = len(video_files)

        logger.debug(f"CSV files: {csv_count}, Video files: {video_count}, CSV processes: {len(csv_processes)}, Video processes: {len(video_processes)}")

        # cleanup finished processes
        csv_processes = cleanup_finished_processes(csv_processes, "CSV")
        video_processes = cleanup_finished_processes(video_processes, "Video")

        if csv_count == 0 and video_count == 0 and len(csv_processes) == 0 and len(video_processes) == 0:
            logger.debug("No files to upload, sleeping...")
            time.sleep(5)
            continue

        # kill ALL video processes if csv count exceeds max
        if csv_count > max_csv_count and len(video_processes) > 0:
            logger.warning(f"CSV count ({csv_count}) exceeds max ({max_csv_count}), killing ALL video upload processes")
            video_processes = terminate_all_processes(video_processes, "Video")

        # spawn CSV upload processes
        if csv_count > 0 and len(csv_processes) < MAX_PROCESSES_PER_FILETYPE:
            files_being_uploaded = get_files_being_uploaded(csv_processes)
            available_files = [f for f in csv_files if str(f) not in files_being_uploaded]
            files_to_upload = get_files_to_upload_parallel(
                available_files,
                extract_data_type_from_csv,
                MAX_PROCESSES_PER_FILETYPE - len(csv_processes)
            )

            for file_to_upload in files_to_upload:
                if len(csv_processes) >= MAX_PROCESSES_PER_FILETYPE:
                    break
                logger.info(f"Spawning CSV upload process for {file_to_upload.name}")
                proc = multiprocessing.Process(
                    target=csv_upload_process,
                    args=(str(file_to_upload),),
                    name=f"csv upload ({file_to_upload.name})"
                )
                proc.start()
                csv_processes.append((proc, str(file_to_upload)))

        # spawn video upload processes (only if csv count below threshold)
        if video_count > 0 and len(video_processes) < MAX_PROCESSES_PER_FILETYPE:
            if csv_count < prioritize_csv_count:
                files_being_uploaded = get_files_being_uploaded(video_processes)
                available_files = [f for f in video_files if str(f) not in files_being_uploaded]
                files_to_upload = get_files_to_upload_parallel(
                    available_files,
                    extract_data_type_from_video,
                    MAX_PROCESSES_PER_FILETYPE - len(video_processes)
                )

                for file_to_upload in files_to_upload:
                    if len(video_processes) >= MAX_PROCESSES_PER_FILETYPE:
                        break
                    logger.info(f"Spawning video upload process for {file_to_upload.name}")
                    proc = multiprocessing.Process(
                        target=video_upload_process,
                        args=(str(file_to_upload),),
                        name=f"video upload ({file_to_upload.name})"
                    )
                    proc.start()
                    video_processes.append((proc, str(file_to_upload)))
            else:
                logger.debug(f"CSV count ({csv_count}) >= prioritize threshold ({prioritize_csv_count}), not starting video uploads")

        time.sleep(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        sys.exit(0)
