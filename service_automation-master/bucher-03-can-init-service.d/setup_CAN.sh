#!/bin/bash 
# sudo busybox devmem 0x0c303010 w 0x400
# sudo busybox devmem 0x0c303018 w 0x458
# add can drivers to the kernel 
#sudo modprobe can
#sudo modprobe can_raw
sudo modprobe mttcan
# setup and bring up can0 interface 
# sudo ip link set can0 up type can bitrate 250000 berr-reporting on 
sudo ip link set can0 type can bitrate 250000 berr-reporting on  restart-ms 2000
sudo ip link set can0 up 
