#!/bin/bash


#!/bin/bash

# Variables
RETRY_INTERVAL=15  # Seconds to wait between retries
MAX_RETRIES=0     # Set to 0 for infinite retries
RETRY_COUNT=0     # Counter for retries

setup_can() {
    # Load required kernel modules
    /usr/sbin/modprobe mttcan
    /usr/sbin/modprobe can_raw
    /usr/sbin/modprobe can

    # Configure CAN interface
    /usr/bin/ip link set can0 type can bitrate 250000 berr-reporting on restart-ms 2000
    if [ $? -ne 0 ]; then
        echo "Failed to configure CAN0 interface."
        return 1
    fi

    # Bring up the CAN interface
    /usr/bin/ip link set can0 up
    if [ $? -ne 0 ]; then
        echo "Failed to bring up CAN0 interface."
        return 1
    fi

    # Verify the interface is up
    STATUS=$(ip link show can0 | grep -o "state UP")
    if [ "$STATUS" != "state UP" ]; then
        echo "CAN0 interface is not in UP state."
        return 1
    fi

    echo "CAN0 interface is up and running."
    return 0
}

# Retry logic
while true; do
    setup_can
    if [ $? -eq 0 ]; then
        # Successful setup
        exit 0
    else
        # Failed setup
        echo "Setup failed. Retrying in $RETRY_INTERVAL seconds..."
        RETRY_COUNT=$((RETRY_COUNT + 1))

        # Check for maximum retries
        if [ "$MAX_RETRIES" -ne 0 ] && [ "$RETRY_COUNT" -ge "$MAX_RETRIES" ]; then
            echo "Maximum retries reached ($MAX_RETRIES). Exiting."
            exit 1
        fi

        sleep "$RETRY_INTERVAL"
    fi
done

