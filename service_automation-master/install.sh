#!/bin/bash

# Exit immediately if a command exits with a non-zero status
set -e

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

# Ensure the installer is executable
chmod +x "$SCRIPT_DIR/service-installer.sh"

# Define services to install.
# If this array is empty, all services will be installed.
# If populated, ONLY these services will be installed; others will be skipped.
SERVICES_TO_INSTALL=(
    "bucher-01-gpio-export-service.d"
    "bucher-02-gpio-monitor-service.d"
    "bucher-03-can-init-service.d"
)

# Variable to hold the backup file path
SKIP_BACKUP_FILE=""

# Function to restore skip files state
restore_skip_files() {
    if [ -n "$SKIP_BACKUP_FILE" ] && [ -f "$SKIP_BACKUP_FILE" ]; then
        echo "Restoring 'skip' files state..."
        # Remove all current skip files in the service directories (depth 2 covers .d/skip)
        find "$SCRIPT_DIR" -maxdepth 2 -name skip -delete
        
        # Restore original skip files
        while read -r skip_file; do
            # Ensure the directory still exists before touching
            if [ -d "$(dirname "$skip_file")" ]; then
                touch "$skip_file"
            fi
        done < "$SKIP_BACKUP_FILE"
        
        rm "$SKIP_BACKUP_FILE"
    fi
}

if [ ${#SERVICES_TO_INSTALL[@]} -gt 0 ]; then
    echo "Filtering services based on configuration..."
    
    # Backup current skip files
    SKIP_BACKUP_FILE=$(mktemp)
    find "$SCRIPT_DIR" -maxdepth 2 -name skip > "$SKIP_BACKUP_FILE"
    
    # Ensure cleanup on exit
    trap restore_skip_files EXIT

    for dir in "$SCRIPT_DIR"/*.d; do
        [ -d "$dir" ] || continue
        dirname=$(basename "$dir")
        should_install=0
        for service in "${SERVICES_TO_INSTALL[@]}"; do
            if [[ "$service" == "$dirname" ]]; then
                should_install=1
                break
            fi
        done

        if [ $should_install -eq 1 ]; then
            # Remove skip file if it exists to ensure installation
            [ -f "$dir/skip" ] && rm "$dir/skip"
        else
            # Create skip file to prevent installation
            [ ! -f "$dir/skip" ] && touch "$dir/skip"
        fi
    done
fi

echo "Running service installer from install.sh..."

# Run the service installer script
# This is intended for automated environments (e.g. QEMU)
"$SCRIPT_DIR/service-installer.sh" --install "$SCRIPT_DIR"
