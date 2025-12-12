#!/bin/bash
# SmartAssist Model Weights Download Script
#
# This script downloads pre-trained model weights for:
# - CSI (Road Segmentation & Garbage Detection)
# - Nozzlenet (Object Detection)
#
# USAGE:
#   ./download_models.sh [--help] [--csi-only] [--nozzlenet-only]
#
# EXIT CODES:
#   0 - Success
#   1 - Error occurred

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Script configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Model URLs (UPDATE THESE WITH ACTUAL URLs)
CSI_ROAD_MODEL_URL="https://your-storage.example.com/models/csi/road_segmentation_v1.0.0.plan"
CSI_GARBAGE_MODEL_URL="https://your-storage.example.com/models/csi/garbage_detection_v1.0.0.plan"
NOZZLENET_MODEL_URL="https://your-storage.example.com/models/nozzlenet/nozzlenet_v2.5.3.plan"

# Model directories
CSI_WEIGHTS_DIR="$REPO_ROOT/models/csi/weights/v1.0.0"
NOZZLENET_WEIGHTS_DIR="$REPO_ROOT/models/nozzlenet/weights/v2.5.3"

# Function to print colored messages
print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to show help
show_help() {
    cat << EOF
SmartAssist Model Weights Download Script

USAGE:
    ./download_models.sh [OPTIONS]

OPTIONS:
    --help              Show this help message
    --csi-only          Download only CSI models
    --nozzlenet-only    Download only Nozzlenet models
    --force             Re-download even if models exist

DESCRIPTION:
    Downloads pre-trained model weights for SmartAssist AI models.
    Models are downloaded to:
        - CSI: models/csi/weights/v1.0.0/
        - Nozzlenet: models/nozzlenet/weights/v2.5.3/

EXAMPLES:
    # Download all models
    ./download_models.sh

    # Download only CSI models
    ./download_models.sh --csi-only

    # Force re-download
    ./download_models.sh --force

NOTE:
    This script requires wget or curl to be installed.
    Model files are large (100MB-500MB each).

EOF
}

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to download file
download_file() {
    local url="$1"
    local output="$2"
    
    print_info "Downloading: $(basename "$output")"
    
    if command_exists wget; then
        wget -q --show-progress "$url" -O "$output"
    elif command_exists curl; then
        curl -# -L "$url" -o "$output"
    else
        print_error "Neither wget nor curl found. Please install one of them."
        return 1
    fi
    
    if [ $? -eq 0 ]; then
        print_info "✓ Downloaded successfully"
        return 0
    else
        print_error "✗ Download failed"
        return 1
    fi
}

# Function to download CSI models
download_csi_models() {
    print_info "Downloading CSI models..."
    
    # Create directories
    mkdir -p "$CSI_WEIGHTS_DIR"
    
    # Download road segmentation model
    if [ ! -f "$CSI_WEIGHTS_DIR/road_segmentation.plan" ] || [ "$FORCE" = true ]; then
        download_file "$CSI_ROAD_MODEL_URL" "$CSI_WEIGHTS_DIR/road_segmentation.plan" || return 1
    else
        print_info "Road segmentation model already exists (use --force to re-download)"
    fi
    
    # Download garbage detection model
    if [ ! -f "$CSI_WEIGHTS_DIR/garbage_detection.plan" ] || [ "$FORCE" = true ]; then
        download_file "$CSI_GARBAGE_MODEL_URL" "$CSI_WEIGHTS_DIR/garbage_detection.plan" || return 1
    else
        print_info "Garbage detection model already exists (use --force to re-download)"
    fi
    
    print_info "✓ CSI models downloaded"
    return 0
}

# Function to download Nozzlenet models
download_nozzlenet_models() {
    print_info "Downloading Nozzlenet models..."
    
    # Create directories
    mkdir -p "$NOZZLENET_WEIGHTS_DIR"
    
    # Download nozzlenet model
    if [ ! -f "$NOZZLENET_WEIGHTS_DIR/nozzlenet.plan" ] || [ "$FORCE" = true ]; then
        download_file "$NOZZLENET_MODEL_URL" "$NOZZLENET_WEIGHTS_DIR/nozzlenet.plan" || return 1
    else
        print_info "Nozzlenet model already exists (use --force to re-download)"
    fi
    
    print_info "✓ Nozzlenet models downloaded"
    return 0
}

# Main function
main() {
    # Parse arguments
    DOWNLOAD_CSI=true
    DOWNLOAD_NOZZLENET=true
    FORCE=false
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            --help)
                show_help
                exit 0
                ;;
            --csi-only)
                DOWNLOAD_CSI=true
                DOWNLOAD_NOZZLENET=false
                shift
                ;;
            --nozzlenet-only)
                DOWNLOAD_CSI=false
                DOWNLOAD_NOZZLENET=true
                shift
                ;;
            --force)
                FORCE=true
                shift
                ;;
            *)
                print_error "Unknown option: $1"
                echo "Use --help for usage information"
                exit 1
                ;;
        esac
    done
    
    # Print header
    echo "=========================================="
    echo "SmartAssist Model Download"
    echo "=========================================="
    echo ""
    
    # Check dependencies
    if ! command_exists wget && ! command_exists curl; then
        print_error "Neither wget nor curl found!"
        print_error "Please install one: sudo apt-get install wget"
        exit 1
    fi
    
    # Check if model URLs are configured
    if [[ "$CSI_ROAD_MODEL_URL" == *"example.com"* ]]; then
        print_warn "Model URLs are not configured!"
        echo ""
        print_info "Please update this script with actual model URLs, or"
        print_info "manually download models to:"
        echo "  - $CSI_WEIGHTS_DIR/"
        echo "  - $NOZZLENET_WEIGHTS_DIR/"
        echo ""
        print_info "Contact your system administrator for model URLs."
        exit 1
    fi
    
    # Download models
    if [ "$DOWNLOAD_CSI" = true ]; then
        download_csi_models || exit 1
    fi
    
    if [ "$DOWNLOAD_NOZZLENET" = true ]; then
        download_nozzlenet_models || exit 1
    fi
    
    # Success
    echo ""
    echo "=========================================="
    print_info "✓ Model download complete!"
    echo "=========================================="
    echo ""
    print_info "Models installed at:"
    [ "$DOWNLOAD_CSI" = true ] && echo "  - $CSI_WEIGHTS_DIR/"
    [ "$DOWNLOAD_NOZZLENET" = true ] && echo "  - $NOZZLENET_WEIGHTS_DIR/"
    echo ""
    
    return 0
}

# Run main function
main "$@"