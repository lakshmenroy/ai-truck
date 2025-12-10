#!/bin/bash -e
/usr/bin/sudo ip link set can0 down
/usr/bin/sudo rmmod mttcan
# /usr/bin/sudo rmmod can_raw
# /usr/bin/sudo rmmod can
