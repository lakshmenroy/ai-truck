#!/bin/bash

# CAN interface
CAN_INTERFACE=can0
# Specific CAN ID to listen for
CAN_ID=284
# Number of attempts to check for CAN ID
NUM_ATTEMPTS=5
# Waiting time between attempts (in seconds)
WAIT_TIME=60

for ((i=1; i<=$NUM_ATTEMPTS; i++)); do
    if timeout --foreground 3 candump $CAN_INTERFACE | grep " $CAN_ID "; then
        echo "CAN ID 0x$CAN_ID messages detected, proceeding to set time if necessary."

        # IMPORTANT: This script depedendencies must be met on the target system for it to exit sucessfully (check README for more info)
        # /usr/bin/python3 /mnt/ssd/workspace/ganindu_ws/services_automation/bucher-4-can-time-update-service.d/CAN_time_setter_script.py
        /usr/bin/python /usr/local/sbin/bucher/CAN_time_setter_script.py
        exit_status=$?
        if [ $exit_status -eq 0 ]; then
            echo "Time set script executed successfully."
        else
            echo "Time set failed."
        fi
        exit $exit_status
    else
        echo "CAN ID $CAN_ID not found, checking again in $WAIT_TIME seconds."
        sleep $WAIT_TIME
    fi
done

echo "CAN ID $CAN_ID not found after $NUM_ATTEMPTS attempts. Exiting with failure."
exit 1

