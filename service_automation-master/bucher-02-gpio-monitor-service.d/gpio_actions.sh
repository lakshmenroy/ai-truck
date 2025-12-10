#!/bin/bash

LOCK_FILE_="/run/lock/bucher_gpio_monitor_executable.lock"

# Attempt to create a lock file
if [ -e "$LOCK_FILE_" ]; then
    echo "Another instance is running." >&2
    exit 1
else
    touch "$LOCK_FILE_"
    # Ensure the lock file is removed when the script exits
    trap 'rm -f "$LOCK_FILE_"' EXIT
fi

check_if_pid_exists() {
    pid=$1
    if ps -p "$pid" > /dev/null; then
        return 0
    else
        echo "Function: ${FUNCNAME[0]} | Line $LINENO: Process with PID $pid is not running"
        return 1
    fi
}

get_smart_sweeper_app_pid() {
    filename="${1:-/run/bucher_smart_sweeper_app/smart_sweeper_main_app.pid}" 
    process_name="${2:-bucher-custom-video-test-launcher}" 

    SMART_SWEEPER_APP_PID=$(cat "$filename" 2>/dev/null)
    if [ -z "$SMART_SWEEPER_APP_PID" ]; then
        echo "Function: ${FUNCNAME[0]} | Line $LINENO: Smart sweeper app PID not found, searching for the PID"
        SMART_SWEEPER_APP_PID=$(pgrep -f "$process_name")

        if [ -z "$SMART_SWEEPER_APP_PID" ]; then
            echo "Function: ${FUNCNAME[0]} | Line $LINENO: Smart sweeper app PID not found, exiting"
            return 1  # Indicates failure or non-existence
        fi
    fi
    echo "$SMART_SWEEPER_APP_PID"
    return 0  # Indicates success
}

handleSmartSweeperAppShutdown() {
    if [ -z "${SMART_SWEEPER_APP_PID}" ]; then
        echo "SMART_SWEEPER_APP_PID is not set, skipping smart sweeper app shutdown"
        return
    elif [ "$SMART_SWEEPER_APP_PID" -eq -1 ]; then
        echo "SMART_SWEEPER_APP_PID is set to -1, indicating no running app. Moving to next condition."
        return
    else
        if check_if_pid_exists "$SMART_SWEEPER_APP_PID"; then
            echo "Function: ${FUNCNAME[0]} | Line $LINENO: IGNITION signal is off, attempting to stop the smart sweeper app with PID $SMART_SWEEPER_APP_PID"
            kill -SIGINT "$SMART_SWEEPER_APP_PID"
            sleep "${SECONDS_TO_WAIT_AFTER_SIGINT_SIGNAL_SENT:-5}"  # Default to 5 seconds if not set
            SECONDS_SINCE_SIGINT_SIGNAL_SENT=0
            while check_if_pid_exists "$SMART_SWEEPER_APP_PID" && [ "$SECONDS_SINCE_SIGINT_SIGNAL_SENT" -lt "${SECONDS_TO_WAIT_BEFORE_FORCE_STOPPING_SERVICE:-60}" ]; do
                sleep 1
                SECONDS_SINCE_SIGINT_SIGNAL_SENT=$((SECONDS_SINCE_SIGINT_SIGNAL_SENT + 1))
            done
            if check_if_pid_exists "$SMART_SWEEPER_APP_PID"; then
                echo "Function: ${FUNCNAME[0]} | Line $LINENO: Smart sweeper app did not stop gracefully, sending a systemctl stop command to the service"
                if [ -z "${SMART_SWEEPER_APP_SERVICE_NAME}" ]; then
                    echo "SMART_SWEEPER_APP_SERVICE_NAME is not set, using backup service name"
                    SMART_SWEEPER_APP_SERVICE_NAME="bucher-custom-video-test-launcher"
                fi
                sudo systemctl stop "$SMART_SWEEPER_APP_SERVICE_NAME"
                SECONDS_SINCE_SYSTEMCTL_STOP_SENT=0
                while check_if_pid_exists "$SMART_SWEEPER_APP_PID" && [ "$SECONDS_SINCE_SYSTEMCTL_STOP_SENT" -lt "${SECONDS_TO_WAIT_BEFORE_FORCE_STOPPING_SERVICE:-60}" ]; do
                    sleep 1
                    SECONDS_SINCE_SYSTEMCTL_STOP_SENT=$((SECONDS_SINCE_SYSTEMCTL_STOP_SENT + 1))
                done
                if check_if_pid_exists "$SMART_SWEEPER_APP_PID"; then
                    echo "Function: ${FUNCNAME[0]} | Line $LINENO: Smart sweeper app did not stop after systemctl stop, sending a kill -9 command to the process"
                    kill -9 "$SMART_SWEEPER_APP_PID"
                fi
            fi
        else
            echo "SMART_SWEEPER_APP_PID is set ($SMART_SWEEPER_APP_PID), but the app is not running. Moving to next condition."
        fi
    fi
}

# Get the PID of the smart sweeper app
SMART_SWEEPER_APP_PID=$(get_smart_sweeper_app_pid "${PID_FILE}" "${SMART_SWEEPER_APP_SERVICE_NAME}")
if [ $? -ne 0 ]; then
    SMART_SWEEPER_APP_PID=-1
fi

# Set timing variables
SECONDS_TO_WAIT_BEFORE_FORCE_STOPPING_SERVICE=15
SECONDS_TO_WAIT_BEFORE_SHUTTING_DOWN_SYSTEM=5
SECONDS_TO_WAIT_AFTER_SIGINT_SIGNAL_SENT=2
SECONDS_TO_WAIT_AFTER_SYSTEMCTL_STOP=10
SECONDS_SINCE_SIGINT_SIGNAL_SENT=0

# Get the GPIO line for PH.01
GPIO_LINE=$(/usr/bin/gpiofind PH.01)
if [ -z "$GPIO_LINE" ]; then
    echo "Failed to find GPIO line for PH.01"
    exit 1
fi

# Read the ignition state using gpioget
IGNITION_STATE=$(/usr/bin/gpioget $GPIO_LINE)
if [ -z "$IGNITION_STATE" ]; then
    echo "Failed to read ignition state. Ignition state is empty."
    exit 1
fi

#echo "IGNITION_STATE: $IGNITION_STATE"

# Compare the ignition state with 0
if [ "$IGNITION_STATE" -eq 0 ]; then
    echo "Ignition signal not present, checking if the smart sweeper app is running"
    # Additional logic here
else
    echo "Ignition signal is present"
fi

# Read the ignition state using gpioget
IGNITION_STATE=$(/usr/bin/gpioget $GPIO_LINE)
echo "IGNITION_STATE: $IGNITION_STATE"

if [ "$IGNITION_STATE" -eq 0 ]; then
    echo "Ignition signal not present, checking if the smart sweeper app is running"
    if [ "$SMART_SWEEPER_APP_PID" -eq -1 ]; then
        unset SMART_SWEEPER_APP_PID
        echo "SMART_SWEEPER_APP_PID is not set, checking other conditions and continuing with the shutdown steps"
    else
        handleSmartSweeperAppShutdown
    fi
    echo "Function: ${FUNCNAME[0]} | Line $LINENO: IGNITION signal is off, waiting for $SECONDS_TO_WAIT_BEFORE_SHUTTING_DOWN_SYSTEM seconds before sending the shutdown signal to the system"
    sleep "$SECONDS_TO_WAIT_BEFORE_SHUTTING_DOWN_SYSTEM"
    echo "Function: ${FUNCNAME[0]} | Line $LINENO: IGNITION signal is off, sending shutdown signal to the system"
    sudo systemctl poweroff
fi

# Return success
exit 0
