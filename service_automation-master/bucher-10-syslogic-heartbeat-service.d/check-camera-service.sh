#!/bin/bash

service="bucher-d3-camera-init.service"
echo "Checking service $service"

# Check if the service was successfully executed
exec_main_status=$(systemctl show -p ExecMainStatus --value "$service")

if [ "$exec_main_status" = "0" ]; then
    echo "$service was successfully executed"
    all_services_active=true
else
    echo "$service was not successfully executed"
    all_services_active=false
fi
