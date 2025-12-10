#!/usr/bin/env python3
"""
    Sets the logging device time to the Proemion device time if they are different. 

    Original Author: Bouchra Mohamed Lemine
    Updated by:  Ganindu Nanayakkara from 28-02-2024

"""

import can
import cantools
from can.interface import Bus
import os
import math
import datetime
import sys


def unix_time_to_utc(unix_time):
    """
    Converts the number of seconds since the Unix epoch to the current date and time (UTC time).
    """

    return datetime.datetime.fromtimestamp(unix_time, datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
    # return datetime.datetime.utcfromtimestamp(unix_time).strftime('%Y-%m-%d %H:%M:%S')
    

def set_date_time(bus, db):
    """
    Decodes the date & time sent by the proemion and compares them to date & time on the logging device. 
    """
    try:
        msg = bus.recv()

        #if bus recv returns None, it means that the message was not received and we do a non zero exit code
        if msg is None:
            print("No message received from the CAN bus")
            exit(-1)

        unix_time = db.decode_message(msg.arbitration_id, msg.data)["Device_Time"]

        # print("unix time from built-in function: ", unix_time_to_utc(int(unix_time)))

        if int(str(datetime.datetime.now().timestamp()).split(".")[0]) != int(unix_time):
            os.system(f"/usr/bin/sudo date -s '{unix_time_to_utc(unix_time + 1)}'") # add one second to copensate for any delays (this is not ideal)
            print(f"Date & time set to {unix_time_to_utc(unix_time + 1)}")
            # print current system unix time and the unix time from the CAN message
            # print("Unix time from CAN: ", unix_time, "Unix time from device: ", int(str(datetime.datetime.now().timestamp()).split(".")[0]))
            return 0
        else:
            pass
            print("Date & time are the same, unix time from CAN: ", unix_time, "unix time from device: ", int(str(datetime.datetime.now().timestamp()).split(".")[0]))
            return 0

    except Exception as e:
        print(e)
        return -1

if __name__ == "__main__":
    print("Starting the CAN time setter script...")

    '''
    @todo: 
            1. Needs to load configuration values from a configuration file, not hard-coded.
            2. use proper logging instead of print statements.
            3. create tests.
    '''

    can.rc['interface'] = 'socketcan'
    can.rc['channel'] = 'can0'
    can.rc['bitrate'] = 250000
    can.rc['can_filters'] = [{"can_id": 0x284, "can_mask": 0xFFF, "extended": False}] # 0x284 is the id of the device time (proemion)

    print("Creating a CAN bus and loading the DBC file...")

    retval = -1

    # Using the context manager to handle the CAN bus connection.
    with Bus() as bus:
        db = cantools.database.load_file('/usr/local/sbin/bucher/basic_comms.dbc')
        # db = cantools.database.load_file('./basic_comms.dbc') 
        print("DBC file loaded...")
        retval = set_date_time(bus, db)

    print("Exiting the CAN time setter script... retval: ", retval)

    # if retval is zero sys.exit(0) else sys.exit(1)
    if retval == 0:
        sys.exit(0)
    else:   
        sys.exit(1)

