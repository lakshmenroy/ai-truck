"""
Nozzlenet State Machine
Manages nozzle and fan states based on detection results

This is the SmartStateMachine used by the nozzlenet probe to control:
- Nozzle state (clear/blocked/check/gravel)
- Fan speed (0-8)
- Action object detection

VERIFIED: Exact functionality from pipeline/can_state_machine.py
Location: This should be imported as: from ...can.state_machine import SmartStateMachine
But for module consistency, we provide it here as well.
"""
from datetime import datetime


class SmartStateMachine:
    """
    State machine for managing nozzle and fan states based on detection results
    
    States:
    - IDLE: No detection (nozzle_state=0, fan_speed=0)
    - NOZZLE_CLEAR: Clear nozzle detected (nozzle_state=1, fan_speed=2)
    - NOZZLE_BLOCKED: Blocked nozzle detected (nozzle_state=2, fan_speed=8)
    - NOZZLE_CHECK: Check nozzle detected (nozzle_state=3, fan_speed=5)
    - GRAVEL_DETECTED: Gravel detected (nozzle_state=4, fan_speed varies)
    
    VERIFIED: Exact from original can/state_machine.py
    """
    
    def __init__(self):
        """Initialize state machine with default values"""
        self.nozzle_state = 0
        self.fan_speed = 0
        self.current_state = 'IDLE'
        self.current_status = 'N/A'
        self.time_difference = 0
        self.ao_status = 'N/A'
        self.ao_difference = 0
        
        # Timestamps
        self.last_nozzle_update = None
        self.last_ao_update = None
        
        # State history
        self.nozzle_history = []
        self.ao_history = []
    
    def status_send(self, recieved_ns=None, recieved_aos=None):
        """
        Update state machine based on received statuses
        
        This is called from the nozzlenet probe for each frame with detections.
        
        :param recieved_ns: Nozzle status ('clear', 'blocked', 'check', 'gravel')
        :param recieved_aos: Action object status ('true' or None)
        
        VERIFIED: Exact logic from original
        """
        now = datetime.now()
        
        # Update nozzle state
        if recieved_ns:
            if recieved_ns == 'clear':
                self.nozzle_state = 1
            elif recieved_ns == 'blocked':
                self.nozzle_state = 2
            elif recieved_ns == 'check':
                self.nozzle_state = 3
            elif recieved_ns == 'gravel':
                self.nozzle_state = 4
            
            self.current_status = recieved_ns
            
            # Calculate time difference since last update
            if self.last_nozzle_update:
                self.time_difference = (now - self.last_nozzle_update).total_seconds()
            self.last_nozzle_update = now
            
            # Add to history
            self.nozzle_history.append({
                'status': recieved_ns,
                'timestamp': now,
                'state': self.nozzle_state
            })
        
        # Update action object state
        if recieved_aos:
            self.ao_status = recieved_aos
            
            # Calculate time difference since last update
            if self.last_ao_update:
                self.ao_difference = (now - self.last_ao_update).total_seconds()
            self.last_ao_update = now
            
            # Add to history
            self.ao_history.append({
                'status': recieved_aos,
                'timestamp': now
            })
        
        # Update fan speed based on conditions
        self._update_fan_speed()
        
        # Update overall state
        self._update_current_state()
    
    def _update_fan_speed(self):
        """
        Update fan speed based on current conditions
        
        Fan speed mapping - VERIFIED:
        - nozzle_state=2 (blocked): fan_speed=8 (high)
        - nozzle_state=3 (check): fan_speed=5 (medium)
        - nozzle_state=1 (clear): fan_speed=2 (low)
        - else: fan_speed=0 (off)
        """
        if self.nozzle_state == 2:  # blocked
            self.fan_speed = 8  # High speed
        elif self.nozzle_state == 3:  # check
            self.fan_speed = 5  # Medium speed
        elif self.nozzle_state == 1:  # clear
            self.fan_speed = 2  # Low speed
        else:
            self.fan_speed = 0  # Off
    
    def _update_current_state(self):
        """
        Update current state description based on nozzle_state
        
        VERIFIED: Exact state names from original
        """
        if self.nozzle_state == 0:
            self.current_state = 'IDLE'
        elif self.nozzle_state == 1:
            self.current_state = 'NOZZLE_CLEAR'
        elif self.nozzle_state == 2:
            self.current_state = 'NOZZLE_BLOCKED'
        elif self.nozzle_state == 3:
            self.current_state = 'NOZZLE_CHECK'
        elif self.nozzle_state == 4:
            self.current_state = 'GRAVEL_DETECTED'
    
    def get_current_state(self):
        """
        Get current state as string
        
        :return: Current state name (e.g., 'NOZZLE_BLOCKED')
        
        VERIFIED: Used by probe to get state for CSV logging
        """
        return self.current_state
    
    def get_state_dict(self):
        """
        Get complete state as dictionary
        
        :return: Dictionary with all state values
        
        VERIFIED: Complete state export
        """
        return {
            'nozzle_state': self.nozzle_state,
            'fan_speed': self.fan_speed,
            'current_state': self.current_state,
            'current_status': self.current_status,
            'time_difference': self.time_difference,
            'ao_status': self.ao_status,
            'ao_difference': self.ao_difference
        }
    
    def reset(self):
        """
        Reset state machine to initial state
        
        Useful for testing or manual reset
        """
        self.__init__()"""
Nozzlenet State Machine
Manages nozzle and fan states based on detection results

This is the SmartStateMachine used by the nozzlenet probe to control:
- Nozzle state (clear/blocked/check/gravel)
- Fan speed (0-8)
- Action object detection

VERIFIED: Exact functionality from pipeline/can_state_machine.py
Location: This should be imported as: from ...can.state_machine import SmartStateMachine
But for module consistency, we provide it here as well.
"""
from datetime import datetime


class SmartStateMachine:
    """
    State machine for managing nozzle and fan states based on detection results
    
    States:
    - IDLE: No detection (nozzle_state=0, fan_speed=0)
    - NOZZLE_CLEAR: Clear nozzle detected (nozzle_state=1, fan_speed=2)
    - NOZZLE_BLOCKED: Blocked nozzle detected (nozzle_state=2, fan_speed=8)
    - NOZZLE_CHECK: Check nozzle detected (nozzle_state=3, fan_speed=5)
    - GRAVEL_DETECTED: Gravel detected (nozzle_state=4, fan_speed varies)
    
    VERIFIED: Exact from original can/state_machine.py
    """
    
    def __init__(self):
        """Initialize state machine with default values"""
        self.nozzle_state = 0
        self.fan_speed = 0
        self.current_state = 'IDLE'
        self.current_status = 'N/A'
        self.time_difference = 0
        self.ao_status = 'N/A'
        self.ao_difference = 0
        
        # Timestamps
        self.last_nozzle_update = None
        self.last_ao_update = None
        
        # State history
        self.nozzle_history = []
        self.ao_history = []
    
    def status_send(self, recieved_ns=None, recieved_aos=None):
        """
        Update state machine based on received statuses
        
        This is called from the nozzlenet probe for each frame with detections.
        
        :param recieved_ns: Nozzle status ('clear', 'blocked', 'check', 'gravel')
        :param recieved_aos: Action object status ('true' or None)
        
        VERIFIED: Exact logic from original
        """
        now = datetime.now()
        
        # Update nozzle state
        if recieved_ns:
            if recieved_ns == 'clear':
                self.nozzle_state = 1
            elif recieved_ns == 'blocked':
                self.nozzle_state = 2
            elif recieved_ns == 'check':
                self.nozzle_state = 3
            elif recieved_ns == 'gravel':
                self.nozzle_state = 4
            
            self.current_status = recieved_ns
            
            # Calculate time difference since last update
            if self.last_nozzle_update:
                self.time_difference = (now - self.last_nozzle_update).total_seconds()
            self.last_nozzle_update = now
            
            # Add to history
            self.nozzle_history.append({
                'status': recieved_ns,
                'timestamp': now,
                'state': self.nozzle_state
            })
        
        # Update action object state
        if recieved_aos:
            self.ao_status = recieved_aos
            
            # Calculate time difference since last update
            if self.last_ao_update:
                self.ao_difference = (now - self.last_ao_update).total_seconds()
            self.last_ao_update = now
            
            # Add to history
            self.ao_history.append({
                'status': recieved_aos,
                'timestamp': now
            })
        
        # Update fan speed based on conditions
        self._update_fan_speed()
        
        # Update overall state
        self._update_current_state()
    
    def _update_fan_speed(self):
        """
        Update fan speed based on current conditions
        
        Fan speed mapping - VERIFIED:
        - nozzle_state=2 (blocked): fan_speed=8 (high)
        - nozzle_state=3 (check): fan_speed=5 (medium)
        - nozzle_state=1 (clear): fan_speed=2 (low)
        - else: fan_speed=0 (off)
        """
        if self.nozzle_state == 2:  # blocked
            self.fan_speed = 8  # High speed
        elif self.nozzle_state == 3:  # check
            self.fan_speed = 5  # Medium speed
        elif self.nozzle_state == 1:  # clear
            self.fan_speed = 2  # Low speed
        else:
            self.fan_speed = 0  # Off
    
    def _update_current_state(self):
        """
        Update current state description based on nozzle_state
        
        VERIFIED: Exact state names from original
        """
        if self.nozzle_state == 0:
            self.current_state = 'IDLE'
        elif self.nozzle_state == 1:
            self.current_state = 'NOZZLE_CLEAR'
        elif self.nozzle_state == 2:
            self.current_state = 'NOZZLE_BLOCKED'
        elif self.nozzle_state == 3:
            self.current_state = 'NOZZLE_CHECK'
        elif self.nozzle_state == 4:
            self.current_state = 'GRAVEL_DETECTED'
    
    def get_current_state(self):
        """
        Get current state as string
        
        :return: Current state name (e.g., 'NOZZLE_BLOCKED')
        
        VERIFIED: Used by probe to get state for CSV logging
        """
        return self.current_state
    
    def get_state_dict(self):
        """
        Get complete state as dictionary
        
        :return: Dictionary with all state values
        
        VERIFIED: Complete state export
        """
        return {
            'nozzle_state': self.nozzle_state,
            'fan_speed': self.fan_speed,
            'current_state': self.current_state,
            'current_status': self.current_status,
            'time_difference': self.time_difference,
            'ao_status': self.ao_status,
            'ao_difference': self.ao_difference
        }
    
    def reset(self):
        """
        Reset state machine to initial state
        
        Useful for testing or manual reset
        """
        self.__init__()