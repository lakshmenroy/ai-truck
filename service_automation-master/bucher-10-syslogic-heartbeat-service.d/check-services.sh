#!/bin/bash

all_services_active=true
echo "Checking services"

# List all active services and filter those starting with 'bucher'
services=$(systemctl list-units --type=service --state=active | grep 'bucher*' | awk '{print $1}')
echo "Services to check: $services"

for service in $services; do
    echo "Checking service $service"
    if ! systemctl is-active --quiet "$service"; then
        all_services_active=false
        echo "$service is not active"
        break
    fi
done

if $all_services_active; then
    echo "All services are active"
else
    echo "Some services are not active"
fi