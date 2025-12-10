# Bucher Smart Sweeper Services 

For the smart sweeper ECU (nvidia Jetson) to work, we need to install some background services, they are the folowing daemons listed below.

1. `GPIO Export`
2. `GPIO Monitor` 
3. `CAN Bus setup` 
4. `System Time setter`
5. `collect JCM serial number`
6. `Camera Init` 
7. `Smart Sweeper inference OR logging services`  

Instaling the services can be done with the specifications set in the [service documentation](https://www.freedesktop.org/software/systemd/man/latest/systemd.service.html)

### GPIO Export 

Runs at systems boot and exports GPIO pins to the userspace, currently this only exports the GPIO pin that is connected to the *IGNITION* signal of the host vehicle.

##### Installing the `bucher-gpio-export.service`

* Service install location `/etc/etc/systemd/system/`
* Install files 
    * [bucher-gpio-export.service](./bucher-1-gpio-export-service.d/bucher-gpio-export.service)


### IGNITION Signal Monitor 

This service watches the the GPIO inputs (that is linked to the Host Vehicle wiring harness) ,in this service the key signal we are looking for is the *IGNITION*
signal that communicates the state JCM we want the AI ECU to be in (powered on or off). an embedded watchdog MCU in the AI ECU ECU monitors the input for initial power up 
but once the power is on if we need to gracefully shutdown the system (before the forced power down is initiated by the embedded MCU) we need to keep an eye of the *IGNITION* signal.

*Note:* 
<div style="font-style: italic">

1. Ideally this should be a target state unique to the AI ECU rather tha the host vehicle, but for now we are using the host vehicle's *IGNITION* signal to control the AI ECU power state as a compromise. </br>
2. systemd-poweroff.service (and the related units) should never be executed directly. Instead, trigger system shutdown with a command such as "systemctl poweroff".

UPDATE Notes (Orin)
Dependencies:
Ensure that the `libgpiod` package is installed as gpiofind and gpioget are part of this package.
Permissions:
The user running the script needs permissions to access the GPIO lines. If running as a service, ensure the service has appropriate permissions or consider running the service as root if security policies allow.
Testing:
Before deploying, test the script manually to ensure it behaves as expected.
Service File Adjustments:
If the name of the GPIO setup service has changed (from bucher-gpio-export.service to bucher-gpio-setup.service), ensure that the Requires and After directives in the service file reflect this.

</div>

##### Installing the `bucher-smart-sweeper-gpio-ignition-signal-monitor.service` 

* Service install location `/etc/etc/systemd/system`
* Dependencies 
    * [`GPIO Export service`](#gpio-export) 

* Conflicts
    * `shutdown.target`

* Install files 
    * [`bucher-smart-sweeper-gpio-ignition-signal-monitor.service`](./bucher-2-gpio-monitor-service.d/bucher-smart-sweeper-gpio-ignition-signal-monitor.service)
    * [`bucher-smart-sweeper-gpio-ignition-signal-monitor.timer`](./bucher-2-gpio-monitor-service.d/bucher-smart-sweeper-gpio-ignition-signal-monitor.timer)

    * Executable file
        * [`gpio-monitor.sh`](./bucher-2-gpio-monitor-service.d/gpio-monitor.sh) 


### CAN init/deinit

Intialises the CAN bus 

CAN init is a service that runs at system boot, once sucessful (once can is intialised) it will exit.
@todo this service should be able to restart the CAN bus if it goes down, but for now it is a simple service that runs at boot.

Note: Currently these services are only initialising and de-initialising `can0` for 250Kbps (these will need to be updated for alternative configurations, After the Launch demo.)

* install files 
    * [`bucher-can-init-250k.service `](./bucher-3-can-init-service.d/bucher-can-init-250k.service)
    * [`bucher-can-deinit.service`](./bucher-3-can-init-service.d/bucher-can-deinit.service)


Therse services can be called upon individually woth the commands 

```bash
sudo systemctl restart bucher-can-init-250k.service
sudo systemctl restart bucher-can-deinit.service
```

also these services can be status-checked,stopped,started,disabled and enabled with the systemctl command. the logs for these services can be viewed with the journalctl command.


##### Installing the CAN Init

* service install location `/etc/etc/systemd/system/bucher-can-init-250k.service`
* service install location `/etc/etc/systemd/system/bucher-can-deinit.service`

### System Time Setter 

Sets the system time by listening to the CAN bus so the time in logfiles are accurate. 
This service depends on the CAN monitor service and is aptly named becase the time updates comes from the CAN bus

@todo: these are not in the scope of the demo but will be needed for the final product.
* If the time is not set the system time will be set to +1 minute from the last known time (this will be stored in a location that will be updated periodilly at rutime )
* A flag will be created to indicate if the time was set by the CAN bus or not (from the last known time), this will be used to indicate if the time is accurate or not. and to parse in log files to avoid descripencies in time and avoid confusion to when and when not we had good GPS time sync.

python package dependencies can time setter script

```bash

pip install can
pip install cantools

```
##### Installing the Time Setter

* service install location `/etc/etc/systemd/system/bucher-can-time-update-service.d`

@todo:  complete this README section, put off becase Launch demo prep is given priority.

### JCM serial number collector

@todo: complete this README section, put off becase Launch demo prep is given priority.

### Camera init

Checks for connected cameras and link Cameras to LVDS ports, This is handy in case the camera detection order is not consistant (the relationship of /dev/videoN assignment with respect to physical camera connectors in the ECU) ideally this should be a service of type notify/notify-reload. 

this service depends on the system time as the resulting output file path is derived based on the system time 

##### Installing the Camera init service 

* service install location `/etc/etc/systemd/system/bucher-camera-init-service.d` 

### SSWP inference/logging service

This service by design shoulld be of type notify/notify-reload, but since the smart sweeper app is not yet ready, we are using the simple type for now.
notify services can communicate the service state to the service manager, this is useful for the smart sweeper app becase we can effectily supervise the service externally and 
communicatewith the vehicle and logging services to inform them of the state of the AI ECU main application.

These services run the smart sweeper app and depends on the Camera init service.

##### Installing the Infer/log service 

* service install location `/etc/etc/systemd/system/bucher-smart-sweeper-service.d`




## KNOWN ISSUES 

The service install order is not enforced, you may need to manipulate the skip files to make sure they install on correct order (e.g. 1, 2, 3 ...)
