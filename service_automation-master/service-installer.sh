#!/bin/bash

# Exit immediately if a command exits with a non-zero status
set -e

# Initialize variables
DRY_RUN=0
INSTALL=0
UNINSTALL=0

# Associative array to track copied files
declare -A COPIED_FILES

# Function to display usage
usage() {
    echo "Usage: $0 [options] [WORKSPACE_DIR]"
    echo "Options:"
    echo "  -h, --help        Show this help message"
    echo "  -n, --dry-run     Perform a dry run (do not make changes)"
    echo "  -i, --install     Install services (default action)"
    echo "  -u, --uninstall   Uninstall services"
    exit 1
}

# Parse command-line options
while [[ $# -gt 0 ]]; do
    case $1 in
        -n|--dry-run)
            DRY_RUN=1
            shift
            ;;
        -i|--install)
            INSTALL=1
            shift
            ;;
        -u|--uninstall)
            UNINSTALL=1
            shift
            ;;
        -h|--help)
            usage
            ;;
        *)
            # Assume any other argument is WORKSPACE_DIR
            WORKSPACE_DIR="$1"
            shift
            ;;
    esac
done

# If neither install nor uninstall is specified, default to install
if [ "$INSTALL" -eq 0 ] && [ "$UNINSTALL" -eq 0 ]; then
    INSTALL=1
fi

# Use the provided directory or default to the directory of this script
WORKSPACE_DIR="${WORKSPACE_DIR:-$(dirname "$0")}"

# Check if the script is running with root privileges
if [ "$(id -u)" != "0" ]; then
    echo "This script must be run as root. Please use sudo."
    exit 1
fi

# Define directories
SYSTEMD_DIR="/etc/systemd/system"
EXECUTABLES_DIR="/usr/local/sbin/bucher" # Dedicated subdirectory for scripts

# Create the executables directory if installing and not a dry run
if [ "$INSTALL" -eq 1 ] && [ "$DRY_RUN" -eq 0 ]; then
    if [ ! -d "$EXECUTABLES_DIR" ]; then
        echo "Creating directory $EXECUTABLES_DIR"
        mkdir -p "$EXECUTABLES_DIR"
        chown root:root "$EXECUTABLES_DIR"
        chmod 755 "$EXECUTABLES_DIR"
    else
        echo "Directory $EXECUTABLES_DIR already exists"
    fi
fi

# Log output to a file
LOG_FILE="/var/log/bucher_install.log"
touch "$LOG_FILE"
chown root:root "$LOG_FILE"
chmod 644 "$LOG_FILE"
exec > >(tee -a "$LOG_FILE") 2>&1

# Create a temporary directory for processing service files
TEMP_WORK_DIR=$(mktemp -d)
cleanup() {
    rm -rf "$TEMP_WORK_DIR"
}
trap cleanup EXIT

echo "==============================="
echo "Bucher Services Installer"
echo "Date: $(date)"
echo "Workspace directory: $WORKSPACE_DIR"
echo "Dry run mode: $DRY_RUN"
echo "Operation: $( [ "$INSTALL" -eq 1 ] && echo "Install" || echo "Uninstall" )"
echo "==============================="
echo

# Automatically find service directories ending with '.d'
SERVICE_DIRS=($(find "$WORKSPACE_DIR" -maxdepth 1 -type d -name "*.d" | sort))

if [ ${#SERVICE_DIRS[@]} -eq 0 ]; then
    echo "No service directories found in $WORKSPACE_DIR"
    exit 0
fi

echo "Found service directories: ${SERVICE_DIRS[@]}"
echo

# Loop through each found service directory
for dir in "${SERVICE_DIRS[@]}"; do
    SERVICE_DIR_NAME=$(basename "$dir")
    echo "Processing $SERVICE_DIR_NAME..."

    # Skip directory if a 'skip' file is present
    if [ -f "$dir/skip" ]; then
        echo "Skipping $SERVICE_DIR_NAME as directed by 'skip' file."
        echo
        continue
    fi

    # Process install.conf
    INSTALL_CONF="$dir/install.conf"
    if [ -f "$INSTALL_CONF" ]; then
        echo "Processing install.conf in $SERVICE_DIR_NAME"
        while IFS='=' read -r source dest; do
            # Remove whitespace
            source="$(echo -e "${source}" | tr -d '[:space:]')"
            dest="$(echo -e "${dest}" | tr -d '[:space:]')"
            # Skip empty lines or comments
            if [[ -z "$source" || -z "$dest" || "$source" == \#* ]]; then
                continue
            fi
            SOURCE_FILE="$dir/$source"
            if [ -f "$SOURCE_FILE" ]; then
                if [ "${COPIED_FILES["$dest"]}" != "1" ]; then
                    if [ "$DRY_RUN" -eq 1 ]; then
                        echo "[DRY RUN] Would copy $SOURCE_FILE to $dest"
                    else
                        echo "Copying $SOURCE_FILE to $dest"
                        mkdir -p "$(dirname "$dest")"
                        cp "$SOURCE_FILE" "$dest"
                        chmod +x "$dest"
                    fi
                    COPIED_FILES["$dest"]=1
                else
                    echo "File $dest already copied, skipping."
                fi
            else
                echo "Error: Source file $SOURCE_FILE does not exist"
                exit 1
            fi
        done < <(grep -E -v '^(\s*#|\s*$)' "$INSTALL_CONF")
    fi

    # Find all .service files first
    SERVICE_FILES=($(find "$dir" -maxdepth 1 -type f -name "*.service" | sort))

    # Then find all .timer files
    TIMER_FILES=($(find "$dir" -maxdepth 1 -type f -name "*.timer" | sort))

    # Combine them, ensuring services come before timers
    FILES=("${SERVICE_FILES[@]}" "${TIMER_FILES[@]}")

    if [ ${#FILES[@]} -eq 0 ]; then
        echo "No .service or .timer files found in $dir"
        echo
        continue
    fi

    # Install unit files without reloading daemon or starting services
    for file in "${FILES[@]}"; do
        FILENAME=$(basename "$file")

        if [ "$DRY_RUN" -eq 1 ]; then
            if [ "$INSTALL" -eq 1 ]; then
                echo "[DRY RUN] Would install $FILENAME to $SYSTEMD_DIR"
            elif [ "$UNINSTALL" -eq 1 ]; then
                echo "[DRY RUN] Would uninstall $FILENAME"
            fi
        else
            if [ "$UNINSTALL" -eq 1 ]; then
                # Stop and disable the service
                echo "Stopping and disabling $FILENAME"
                systemctl stop "$FILENAME" || true
                systemctl disable "$FILENAME" || true

                # Remove the service file
                if [ -f "$SYSTEMD_DIR/$FILENAME" ]; then
                    echo "Removing $FILENAME from $SYSTEMD_DIR"
                    rm "$SYSTEMD_DIR/$FILENAME"
                else
                    echo "$FILENAME not found in $SYSTEMD_DIR, skipping removal."
                fi

                # Remove associated scripts
                echo "Removing associated scripts for $FILENAME"
                # Extract scripts to remove
                SCRIPTS=$(grep -E 'ExecStartPre=|ExecStart=|ExecStartPost=' "$file" | awk -F= '
                BEGIN { OFS = "" }
                {
                    gsub(/^[\\\"\047]|[\\\"\047]$/, "", $2);
                    n = split($2, arr, " ");
                    for (i = 1; i <= n; i++) {
                        if (arr[i] ~ /^\/.*\.sh$/) {
                            print arr[i];
                        }
                    }
                }')

                for script_dest in $SCRIPTS; do
                    if [ -f "$script_dest" ]; then
                        echo "Removing script $script_dest"
                        rm "$script_dest"
                    else
                        echo "Script $script_dest not found, skipping."
                    fi
                done

                echo "$FILENAME uninstalled."
            elif [ "$INSTALL" -eq 1 ]; then
                # Remove existing service/timer files if they exist
                if [ -f "$SYSTEMD_DIR/$FILENAME" ]; then
                    echo "Removing existing file: $FILENAME from $SYSTEMD_DIR"
                    rm "$SYSTEMD_DIR/$FILENAME"
                fi

                # Create a temporary file for the service content to modify paths
                TEMP_SERVICE_FILE="$TEMP_WORK_DIR/$FILENAME"
                cp "$file" "$TEMP_SERVICE_FILE"

                # Find all script files (.sh and .py) in the current directory
                SCRIPT_FILES=($(find "$dir" -maxdepth 1 -type f \( -name "*.sh" -o -name "*.py" \)))

                for script in "${SCRIPT_FILES[@]}"; do
                    SCRIPT_NAME=$(basename "$script")
                    DEST_SCRIPT="$EXECUTABLES_DIR/$SCRIPT_NAME"

                    # ALWAYS copy the script to EXECUTABLES_DIR to ensure dependencies are met
                    # (e.g. script A calls script B, but only A is referenced in the service file)
                    if [ "${COPIED_FILES["$DEST_SCRIPT"]}" != "1" ]; then
                        echo "Installing script $SCRIPT_NAME to $DEST_SCRIPT"
                        mkdir -p "$(dirname "$DEST_SCRIPT")"
                        cp "$script" "$DEST_SCRIPT"
                        chmod +x "$DEST_SCRIPT"
                        COPIED_FILES["$DEST_SCRIPT"]=1
                    fi
                    
                    # Find tokens in the service file that end with this script name
                    # We look for strings that might be paths (no spaces/quotes)
                    MATCHES=$(grep -oE "[^ \"'=\t]*$SCRIPT_NAME" "$TEMP_SERVICE_FILE" || true)

                    for match in $MATCHES; do
                        # Check if the basename of the match is exactly the script name
                        # This prevents 'script.sh' matching 'myscript.sh'
                        MATCH_BASENAME=$(basename "$match")
                        if [ "$MATCH_BASENAME" == "$SCRIPT_NAME" ]; then
                            echo "Found script usage: $match -> $DEST_SCRIPT"
                            
                            # Replace the path in the temp service file
                            # Use | as delimiter for sed
                            sed -i "s|$match|$DEST_SCRIPT|g" "$TEMP_SERVICE_FILE"
                        fi
                    done
                done

                # Copy new service/timer files to systemd directory
                echo "Installing $FILENAME to $SYSTEMD_DIR"
                cp "$TEMP_SERVICE_FILE" "$SYSTEMD_DIR/$FILENAME"
                rm "$TEMP_SERVICE_FILE"
            fi
        fi
    done

    # After installing all unit files, reload systemd daemon
    if [ "$DRY_RUN" -eq 0 ]; then
        echo "Reloading systemd daemon..."
        systemctl daemon-reload
    fi

    # Enable and start the services and timers
    for file in "${FILES[@]}"; do
        FILENAME=$(basename "$file")

        if [ "$DRY_RUN" -eq 1 ]; then
            if [ "$INSTALL" -eq 1 ]; then
                echo "[DRY RUN] Would enable and start $FILENAME"
            elif [ "$UNINSTALL" -eq 1 ]; then
                echo "[DRY RUN] Would stop and disable $FILENAME"
            fi
        else
            if [ "$UNINSTALL" -eq 1 ]; then
                # Already handled above
                continue
            elif [ "$INSTALL" -eq 1 ]; then
                if [[ "$FILENAME" == *.service ]]; then
                    echo "Enabling $FILENAME"
                    systemctl enable "$FILENAME"
                    echo "Starting/Restarting $FILENAME"
                    systemctl restart "$FILENAME"
                    echo "$FILENAME enabled and started."
                elif [[ "$FILENAME" == *.timer ]]; then
                    echo "Enabling $FILENAME"
                    systemctl enable "$FILENAME"
                    echo "Starting $FILENAME"
                    systemctl start "$FILENAME"
                    echo "$FILENAME enabled and started."
                fi
            fi
        fi
    done

    echo
done

echo "Operation completed."
