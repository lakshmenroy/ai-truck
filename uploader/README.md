# SmartAssist Uploader

## prerequisites
- Python 3
- pip3

i.e. apt-get install python3-pip

# Non Packaged build

## Build

./build-no-package will generate you all necessary files in /build/

# Run

```bash
cd build
./bin/uploader.py
```


# Debian Package build

This builds a debian package which contains everything needed to run the SmartAssist Uploader.
just install and configure via the config.json

## Build

Need Debian system with dpkg.

```bash
./build-deb.sh
```

Makes `dist/smartassist-uploader_1.0.0_all.deb`. Works on amd64 and arm64.

## Install

```bash
sudo dpkg -i dist/smartassist-uploader_1.0.0_all.deb
sudo apt-get install -f
```

## Structure

```
/mnt/syslogic_sd_card/
├── bin/uploader.py
├── config.json.example
├── config.json
├── upload/csv/
├── upload/video/
├── uploaded/csv/
└── uploaded/video/

/lib/systemd/system/smartassist-uploader.service
```

## Config

Put your Azure credentials in `/mnt/syslogic_sd_card/config.json`:

```json
{
    "blob_endpoint": "https://your-account.blob.core.windows.net/container/",
    "sas_token": "?sp=racwdl&st=...",
    "csv_to_upload_dir": "/mnt/syslogic_sd_card/upload/csv",
    "video_to_upload_dir": "/mnt/syslogic_sd_card/upload/video",
    "csv_uploaded_dir": "/mnt/syslogic_sd_card/uploaded/csv",
    "video_uploaded_dir": "/mnt/syslogic_sd_card/uploaded/video",
    "prioritize_csv_count": "10",
    "max_csv_count": "20",
    "log_level": "info"
}
```

## Service

```bash
sudo systemctl status smartassist-uploader
sudo journalctl -u smartassist-uploader -f
sudo systemctl restart smartassist-uploader
```

Service restarts automatic when crash. 10 sec delay, max 5 times in 5 min.

## Remove

```bash
sudo dpkg -r smartassist-uploader
```

Config files stay on disk after remove.
