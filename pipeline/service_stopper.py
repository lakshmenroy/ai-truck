
"""
try this with unix command as well (with sudo apt-get install socat)

echo -n "stop" | socat - UNIX-CONNECT:/tmp/smart_sweeper_pipeline_comms_socket

# echo stop | socat - UNIX-CONNECT:/tmp/smart_sweeper_pipeline_comms_socket

#!/bin/bash

# Define the path to the Unix socket
SOCKET_PATH="/tmp/smart_sweeper_pipeline_comms_socket"

# Define the command to send
COMMAND="stop"

# Check if socat is installed
if ! command -v socat &> /dev/null
then
    echo "socat could not be found. Please install it to use this script."
    exit 1
fi

# Use socat to send the command to the Unix socket
echo $COMMAND | socat - UNIX-CONNECT:$SOCKET_PATH

# Optional: Check the exit status of socat to verify success
if [ $? -eq 0 ]; then
    echo "Command '$COMMAND' sent successfully."
else
    echo "Failed to send command '$COMMAND'."
fi

"""

# @todo: after stop comand is set check for ths systemctl service for a bit and stop it if it is still running

import socket
import sys
import time
import os

def send_stop_command(socket_path):
    # Create a UNIX domain socket
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        try:
            # Connect the socket to the path where the server is listening
            sock.connect(socket_path)
            # Send the "stop" command
            sock.sendall(b'stop')
            print("Stop command sent.")
        except socket.error as msg:
            print(f"Socket error: {msg}")
        finally:
            print("Closing client socket.")

if __name__ == "__main__":
    socket_path = "/tmp/smart_sweeper_pipeline_comms_socket"
    send_stop_command(socket_path)

    # after 10 senconds send "sudo systemctl stop  bucher-custom-video-test-launcher" to stop the service 
    # if it is still running
    time.sleep(10)
    os.system("sudo systemctl stop bucher-custom-video-test-launcher")
    
