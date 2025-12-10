#!/bin/bash

service="bucher-d3-camera-init.service"
echo "Checking service $service"

exec_main_status=$(systemctl show -p ExecMainStatus --value "$service")

if [ "$exec_main_status" = "0" ]; then
    echo "$service was successfully executed"
    all_services_active=true
else
    echo "$service was not successfully executed"
    all_services_active=false
fi

if test -f "/run/bucher_smart_sweeper_app/smart_sweeper_main_app.pid"; then
    cansend can0 777#04
elif ! test -f "/run/bucher_smart_sweeper_app/smart_sweeper_main_app.pid" && $all_services_active; then
    cansend can0 777#00
else 
    cansend can0 777#FF
fi