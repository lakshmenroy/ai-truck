#!/bin/bash
# SmartAssist Health Monitor Script
# Checks status of all smartassist-* services and reports health
#
# Usage: ./check_services.sh
# Exit codes: 0 = all healthy, 1 = some services failed

# Configuration
SERVICE_PREFIX="smartassist-"
LOG_FILE="/var/log/smartassist/health-monitor.log"
STATUS_FILE="/var/lib/smartassist/service_status.json"

# Colors for console output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Ensure directories exist
mkdir -p "$(dirname "$LOG_FILE")"
mkdir -p "$(dirname "$STATUS_FILE")"

log() {
    echo "[Health Monitor] $1"
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >> "$LOG_FILE"
    logger -t smartassist-health "$1"
}

log_success() {
    echo -e "${GREEN}[Health Monitor] $1${NC}"
    echo "$(date '+%Y-%m-%d %H:%M:%S') - SUCCESS: $1" >> "$LOG_FILE"
    logger -t smartassist-health "SUCCESS: $1"
}

log_warning() {
    echo -e "${YELLOW}[Health Monitor] WARNING: $1${NC}"
    echo "$(date '+%Y-%m-%d %H:%M:%S') - WARNING: $1" >> "$LOG_FILE"
    logger -t smartassist-health "WARNING: $1"
}

log_error() {
    echo -e "${RED}[Health Monitor] ERROR: $1${NC}"
    echo "$(date '+%Y-%m-%d %H:%M:%S') - ERROR: $1" >> "$LOG_FILE"
    logger -t smartassist-health "ERROR: $1"
}

# Get list of all smartassist services
log "Checking SmartAssist services..."

# Get active services
SERVICES=$(systemctl list-units --type=service --state=active,failed,inactive \
    | grep "${SERVICE_PREFIX}" \
    | awk '{print $1}' \
    | sort)

if [ -z "$SERVICES" ]; then
    log_warning "No SmartAssist services found!"
    exit 0
fi

# Count services
TOTAL=0
ACTIVE=0
FAILED=0
INACTIVE=0

# Check each service
log "Found services to check:"
ALL_HEALTHY=true

# Start JSON status
echo "{" > "$STATUS_FILE"
echo "  \"timestamp\": \"$(date -Iseconds)\"," >> "$STATUS_FILE"
echo "  \"services\": {" >> "$STATUS_FILE"

FIRST=true

for service in $SERVICES; do
    TOTAL=$((TOTAL + 1))
    
    # Get service status
    if systemctl is-active --quiet "$service"; then
        STATUS="active"
        ACTIVE=$((ACTIVE + 1))
        log_success "✓ $service is ACTIVE"
    elif systemctl is-failed --quiet "$service"; then
        STATUS="failed"
        FAILED=$((FAILED + 1))
        ALL_HEALTHY=false
        log_error "✗ $service is FAILED"
    else
        STATUS="inactive"
        INACTIVE=$((INACTIVE + 1))
        log_warning "⚠ $service is INACTIVE"
    fi
    
    # Add to JSON (with comma if not first)
    if [ "$FIRST" = true ]; then
        FIRST=false
    else
        echo "," >> "$STATUS_FILE"
    fi
    
    echo -n "    \"$service\": {" >> "$STATUS_FILE"
    echo -n "\"status\": \"$STATUS\"" >> "$STATUS_FILE"
    
    # Get uptime if active
    if [ "$STATUS" == "active" ]; then
        UPTIME=$(systemctl show "$service" --property=ActiveEnterTimestamp --value)
        echo -n ", \"since\": \"$UPTIME\"" >> "$STATUS_FILE"
    fi
    
    echo -n "}" >> "$STATUS_FILE"
done

# Close JSON
echo "" >> "$STATUS_FILE"
echo "  }," >> "$STATUS_FILE"
echo "  \"summary\": {" >> "$STATUS_FILE"
echo "    \"total\": $TOTAL," >> "$STATUS_FILE"
echo "    \"active\": $ACTIVE," >> "$STATUS_FILE"
echo "    \"failed\": $FAILED," >> "$STATUS_FILE"
echo "    \"inactive\": $INACTIVE" >> "$STATUS_FILE"
echo "  }" >> "$STATUS_FILE"
echo "}" >> "$STATUS_FILE"

# Summary
log "========================================="
log "Total services: $TOTAL"
log "Active: $ACTIVE"
log "Failed: $FAILED"
log "Inactive: $INACTIVE"
log "========================================="

if [ "$ALL_HEALTHY" = true ]; then
    log_success "All SmartAssist services are healthy"
    exit 0
else
    log_error "Some SmartAssist services have issues"
    
    # List failed services
    log "Failed services:"
    systemctl list-units --type=service --state=failed \
        | grep "${SERVICE_PREFIX}" \
        | awk '{print $1}' \
        | while read -r failed_service; do
            log_error "  - $failed_service"
        done
    
    exit 1
fi
