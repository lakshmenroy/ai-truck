# Number of input video streams to process in parallel
NUM_STREAMS = 2

# === NvStreamMux (stream multiplexer) settings ===
# Timeout (in microseconds) before batching frames from multiple streams
# 33000 µs ≈ 30 FPS, meaning the muxer will wait ~33ms for frames
MUXER_BATCH_TIMEOUT_USEC = 33000

# === Inference Engine (PGIE) configuration files ===
# Paths to config files for primary inference engines (PGIE)
ROAD_PGIE_CONFIG = "/opt/deepstream-app/configs/road_pgie_config.txt"
GARBAGE_PGIE_CONFIG = "/opt/deepstream-app/configs/garbage_pgie_config.txt"
ROAD_UNIQUE_ID = 2
GARBAGE_UNIQUE_ID = 3

# === Performance Callback settings ===
PERF_DATA_TIMEOUT = 5000 # (ms) i.e., 5 seconds