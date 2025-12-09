#!/bin/bash
set -e

PACKAGE_NAME="smartassist-uploader"
VERSION="1.0.0"
MAINTAINER="SmartAssist <marco.meile.ext@buchermunicipal.com>"
DESCRIPTION="Azure Blob Storage Uploader for SmartAssist devices"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTPUT_DIR="${SCRIPT_DIR}/dist"
BUILD_DIR="${SCRIPT_DIR}/build/${PACKAGE_NAME}_${VERSION}_all"
VENDOR_DIR="${BUILD_DIR}/mnt/syslogic_sd_card/bin/vendor"

echo "Building deb package v${VERSION}..."

rm -rf "${BUILD_DIR}"
mkdir -p "${BUILD_DIR}/DEBIAN"
mkdir -p "${BUILD_DIR}/mnt/syslogic_sd_card/bin"
mkdir -p "${BUILD_DIR}/mnt/syslogic_sd_card/upload/csv"
mkdir -p "${BUILD_DIR}/mnt/syslogic_sd_card/upload/video"
mkdir -p "${BUILD_DIR}/mnt/syslogic_sd_card/uploaded/csv"
mkdir -p "${BUILD_DIR}/mnt/syslogic_sd_card/uploaded/video"
mkdir -p "${BUILD_DIR}/lib/systemd/system"

echo "Getting python deps..."
mkdir -p "${VENDOR_DIR}"
pip3 download -r "${SCRIPT_DIR}/requirements.txt" -d "${VENDOR_DIR}/wheels" --no-cache-dir
pip3 install --target="${VENDOR_DIR}" -r "${SCRIPT_DIR}/requirements.txt" --no-cache-dir
rm -rf "${VENDOR_DIR}/wheels"

cp "${SCRIPT_DIR}/uploader.py" "${BUILD_DIR}/mnt/syslogic_sd_card/bin/"
chmod 755 "${BUILD_DIR}/mnt/syslogic_sd_card/bin/uploader.py"

cp "${SCRIPT_DIR}/config.json.example" "${BUILD_DIR}/mnt/syslogic_sd_card/"
cp "${SCRIPT_DIR}/smartassist-uploader.service" "${BUILD_DIR}/lib/systemd/system/"

cat > "${BUILD_DIR}/DEBIAN/control" << EOF
Package: ${PACKAGE_NAME}
Version: ${VERSION}
Section: utils
Priority: optional
Architecture: all
Multi-Arch: foreign
Depends: python3 (>= 3.6)
Maintainer: ${MAINTAINER}
Description: ${DESCRIPTION}
 Upload csv/video to Azure. csv has priority. Systemd service.
EOF

cat > "${BUILD_DIR}/DEBIAN/conffiles" << EOF
/mnt/syslogic_sd_card/config.json.example
EOF

cat > "${BUILD_DIR}/DEBIAN/postinst" << 'EOF'
#!/bin/bash
set -e

if [ ! -f /mnt/syslogic_sd_card/config.json ]; then
    cp /mnt/syslogic_sd_card/config.json.example /mnt/syslogic_sd_card/config.json
    echo "config.json created. Edit with your Azure credentials."
fi

systemctl daemon-reload
systemctl enable smartassist-uploader.service
systemctl start smartassist-uploader.service || true

echo "Service installed. Check: systemctl status smartassist-uploader"
EOF
chmod 755 "${BUILD_DIR}/DEBIAN/postinst"

cat > "${BUILD_DIR}/DEBIAN/prerm" << 'EOF'
#!/bin/bash
set -e

if systemctl is-active --quiet smartassist-uploader.service; then
    systemctl stop smartassist-uploader.service
fi

if systemctl is-enabled --quiet smartassist-uploader.service 2>/dev/null; then
    systemctl disable smartassist-uploader.service
fi

exit 0
EOF
chmod 755 "${BUILD_DIR}/DEBIAN/prerm"

cat > "${BUILD_DIR}/DEBIAN/postrm" << 'EOF'
#!/bin/bash
set -e

systemctl daemon-reload
# keep config and uploaded files
exit 0
EOF
chmod 755 "${BUILD_DIR}/DEBIAN/postrm"

mkdir -p "${OUTPUT_DIR}"
dpkg-deb --build "${BUILD_DIR}" "${OUTPUT_DIR}/${PACKAGE_NAME}_${VERSION}_all.deb"

echo "Done: ${OUTPUT_DIR}/${PACKAGE_NAME}_${VERSION}_all.deb"
