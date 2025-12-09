#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="${SCRIPT_DIR}/build/"
VENDOR_DIR="${BUILD_DIR}/bin/vendor"

rm -rf "${BUILD_DIR}"
mkdir -p "${BUILD_DIR}/bin"
mkdir -p "${BUILD_DIR}/lib/systemd/system"

echo "Getting python deps..."
mkdir -p "${VENDOR_DIR}"
pip3 download -r "${SCRIPT_DIR}/requirements.txt" -d "${VENDOR_DIR}/wheels" --no-cache-dir
pip3 install --target="${VENDOR_DIR}" -r "${SCRIPT_DIR}/requirements.txt" --no-cache-dir
rm -rf "${VENDOR_DIR}/wheels"

cp "${SCRIPT_DIR}/uploader.py" "${BUILD_DIR}/bin/"
chmod 755 "${BUILD_DIR}/bin/uploader.py"

cp "${SCRIPT_DIR}/config.json.example" "${BUILD_DIR}/"
cp "${SCRIPT_DIR}/smartassist-uploader.service" "${BUILD_DIR}/lib/systemd/system/"
