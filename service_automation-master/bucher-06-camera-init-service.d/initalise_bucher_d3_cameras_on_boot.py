
#!/usr/bin/env python3
"""
This script initialises the Bucher D3 cameras on boot.
It is called by the systemd service file: bucher_d3_cameras.service
The service file is located at: /lib/systemd/system/bucher_d3_cameras.service
                    enabled at boot by running: sudo systemctl enable bucher_d3_cameras.service
                    started at boot by running: sudo systemctl start bucher_d3_cameras.service
                    stopped by running: sudo systemctl stop bucher_d3_cameras.service
                    restarted by running: sudo systemctl restart bucher_d3_cameras.service

The service file is status is checked by running: sudo systemctl status bucher_d3_cameras.service
The service file is disabled at boot by running: sudo systemctl disable bucher_d3_cameras.service
The service file is reloaded by running: sudo systemctl daemon-reload


The script initialises the Bucher D3 cameras by:
- reading the configuration file
- creating the AppContext
- testing the cameras
- setting v4l2-ctl settings (but this is not tested yet)

Author: Ganindu Nanayakkara
"""

from app_context import Config, AppContext # this is a local custom module


if __name__ == "__main__":
    config = Config("/usr/local/sbin/bucher/bucher_camera_on_boot_config.json")
    app_context = AppContext(config)

    app_context.initialise_logging()
    app_context.initialise_cameras()
    app_context.export_status_json()



