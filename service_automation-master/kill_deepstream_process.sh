#!/bin/bash

# Path to the PID file
pid_file="/tmp/bucher-deepstream-parallel-infer.pid"

# Check if the PID file exists
if [ -f "$pid_file" ]; then
    # Read the PID from the file
    pid=$(cat "$pid_file")

    # Send SIGINT to the PID
    sudo kill -SIGINT "$pid"
else
    echo "PID file not found."
fi

