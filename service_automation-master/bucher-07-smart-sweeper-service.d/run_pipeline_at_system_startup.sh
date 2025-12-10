#!/bin/bash
# Custom script to launch a GStreamer pipeline and potentially run a Python script

# Get the directory where the script resides
#SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

# Define a function to handle SIGINT
cleanup() {
    echo "Caught SIGINT, cleaning up..."
    # Forward SIGINT to child processes
    pkill -P $$ -SIGINT
    # Perform any additional cleanup if needed
    # ${SCRIPT_DIR}/set_background.sh
    #sudo fbi -T 1 -d /dev/fb0 /mnt/ssd/media/logos/BUC_MUN_Logo_RGB_LAn920x1080_Black_BG_rev_2.png
    exit 0
}

# Trap SIGINT
trap cleanup INT


# Get the directory where the script resides
# these will noe be set by ExecStartPre and ExecStartPost  etc. in the service file
# SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
# ${SCRIPT_DIR}/set_background.sh

# Setting environment variables
# export HOME=/home/ganindu  # Set HOME if not already set
# export PATH="/usr/local/cuda/bin:$PATH"
# export PATH="/usr/src/tensorrt/bin:$PATH"
# export PYENV_ROOT="$HOME/.pyenv"
command -v pyenv >/dev/null || export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv init -)"
eval "$(pyenv virtualenv-init -)"

# GStreamer debug setting
export GST_DEBUG=NVDS_APP:DEBUG


# Unset DISPLAY if it is set
if [ -n "$DISPLAY" ]; then
    unset DISPLAY
fi

#uncomment to run test pipeline 
#gst-launch-1.0 filesrc location="${SCRIPT_DIR}/demo_prep_video0007_fcd.mp4" ! qtdemux name=demux ! h265parse ! nvv4l2decoder ! nvdrmvideosink -e

# Activate Python environment and run GStreamer pipeline
pyenv activate PY3816
# Uncomment to run a Python script in the pyenv environment

#sudo fbi -T 1 -d /dev/fb0 /mnt/ssd/media/logos/BUC_MUN_Logo_RGB_LAn920x1080_Black_BG_rev_2.png

# PYTHON_SCRIPT_DIR="${SCRIPT_DIR}/../scripts"
# cd "$PYTHON_SCRIPT_DIR"
# python camsrc_ssd_300_drm_sink.py


#CPP_RUN_DIR="${SCRIPT_DIR}/../sources/cpp/parallel_pipes"
# CPP_RUN_DIR="/mnt/ssd/workspace/ganindu_ws/sources/cpp/parallel_pipes/"

# cd "$CPP_RUN_DIR"
#sudo GST_DEBUG=NVDS_APP:DEBUG ./apps/deepstream-parallel-infer/deepstream-parallel-infer -c configs/apps/bodypose_yolo/argus_input_2_cameras.yaml --gst-debug=1
#sudo ./apps/deepstream-parallel-infer/deepstream-parallel-infer -c configs/apps/bodypose_yolo/argus_input_2_cameras.yaml  &> /dev/null
# sudo ./apps/deepstream-parallel-infer/deepstream-parallel-infer -c configs/apps/bodypose_yolo/argus_input_4_cameras.yaml  &> /dev/null

PYTHON_SCRIPT_DIR="/mnt/ssd/workspace/ganindu_ws/scripts" # $ python v65e-camera_logger.py
cd "$PYTHON_SCRIPT_DIR"
# python v65e-camera_logger.py


# set background
#sudo fbi -T 1 -d /dev/fb0 /mnt/ssd/media/logos/BUC_MUN_Logo_RGB_LAn920x1080_Black_BG_rev_2.png
${SCRIPT_DIR}/set_background.sh


