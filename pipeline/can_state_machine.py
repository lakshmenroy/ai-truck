'''
Author: Freddie Clarke | Bucher Municipal
Date: 2024-04-29
'''

import asyncio
import time
import can
from statemachine import StateMachine, State
from enum import Enum
from datetime import datetime
import cantools
import threading
import random

class SmartStateMachine(StateMachine):
    '''
    A state machine to control can functions for smart sweeper software
    '''
    debug = 0

    out_of_state = State('out_of_state', value=0, initial=True, enter="on_enter_out_of_state", exit="on_exit_out_of_state")
    check = State('check', value=1, enter="on_enter_check", exit="on_exit_check")
    clear = State('clear', value=2, enter="on_enter_clear", exit="on_exit_clear")
    gravel = State('gravel', value=3, enter="on_enter_gravel", exit="on_exit_gravel")
    blocked  = State('blocked', value=4, enter="on_enter_blocked", exit="on_exit_blocked")
    action_object = State('action_object', value=5, enter="on_enter_action_object", exit="on_exit_action_object")

    out_of_state_to_check = out_of_state.to(check)
    out_of_state_to_clear = out_of_state.to(clear)
    out_of_state_to_blocked = out_of_state.to(blocked)
    out_of_state_to_action_object = out_of_state.to(action_object)
    out_of_state_to_gravel = out_of_state.to(gravel)

    check_to_out_of_state = check.to(out_of_state)
    check_to_clear = check.to(clear)
    check_to_blocked = check.to(blocked)
    check_to_action_object = check.to(action_object)
    check_to_gravel = check.to(gravel)

    clear_to_out_of_state = clear.to(out_of_state)
    clear_to_check = clear.to(check)
    clear_to_blocked = clear.to(blocked)
    clear_to_action_object = clear.to(action_object)
    clear_to_gravel = clear.to(gravel)

    gravel_to_out_of_state = gravel.to(out_of_state)
    gravel_to_check = gravel.to(check)
    gravel_to_clear = gravel.to(clear)
    gravel_to_blocked = gravel.to(blocked)
    gravel_to_action_object = gravel.to(action_object)

    blocked_to_out_of_state = blocked.to(out_of_state)
    blocked_to_check = blocked.to(check)
    blocked_to_clear = blocked.to(clear)
    blocked_to_action_object = blocked.to(action_object)
    blocked_to_gravel = blocked.to(gravel)

    action_object_to_out_of_state = action_object.to(out_of_state)
    action_object_to_check = action_object.to(check)
    action_object_to_clear = action_object.to(clear)
    action_object_to_blocked = action_object.to(blocked)
    action_object_to_gravel = action_object.to(gravel)

    start_time = None
    last_update_time = None
    current_status = None
    action_object_status = None
    action_object_start_time = None
    action_object_last_update_time = None

    can_sent_time = None
    nozzle_state = 0
    fan_speed = 1
    candidate_count = 0

    time_to_activate = 0.3
    time_to_deactivate = 0.6
    stepdown = 0
    stepdown_time = 1
    stepdown_state = None

    bustype = 'socketcan'
    channel = 'can0'
    bus = can.interface.Bus(channel=channel, bustype=bustype)
    check_thread = None
    stop_thread = None
    can_thread = None

    def debug_print(self, *args, **kwargs):
        if self.debug == 1:
            print(*args, **kwargs)
    
    def status_send(self, recieved_ns, recieved_aos):
        '''
        function to update status in the machine and enter state_trigger
        nozzle status list: blocked, unblocked, check
        action object status: True, False
        '''

        if not recieved_ns:
            self.current_status = None
        # if the status that has been recieved is different to the current status we can treat this as if it is the new candidate for state
        if recieved_ns and recieved_ns != self.current_status:
            self.start_time = time.time()
            self.current_status = recieved_ns
        # otherwise the state must match the current status and therefore the current state should remain active
        elif recieved_ns:
            if self.current_status == self.current_state.id:
                self.last_update_time = time.time()
            elif self.current_status != self.current_state.id:
                self.candidate_count += 1
        # as action objects are not mutually exclusive with other statuses it is tracked by itself
        if recieved_aos is None:
            recieved_aos = 'false'
            self.action_object_status = recieved_aos
        # if the action object status does not match the existing status and there is an action object we set this as the start time
        if recieved_aos != self.action_object_status and recieved_aos != 'false':
            self.action_object_start_time = time.time()
            self.action_object_status = recieved_aos
        # if the action object status does match the existing status and there is an action object this becomes the update time to keep the machine in this state
        elif recieved_aos == self.action_object_status and recieved_aos != 'false':
            if self.current_state == self.action_object:
                self.action_object_last_update_time = time.time()
        elif self.current_state != self.action_object:
            self.action_object_start_time = time.time()

        # if there is no nozzle state we reset the activation timer on the basis that the detection is not stable enough to take an action
        if not recieved_ns and self.start_time and time.time() - self.start_time < self.time_to_activate: 
            self.start_time = time.time()

        # see @state_trigger
        self.state_trigger()

        # if after checking for state triggering the nozzle status is None and the status has been active for too long reset the activation timer,
        # this is to prevent say a unblocked being seen once and then multiple None and then one more unblocked triggering an unblocked state as in
        # this situation the time between the two unblocked would be > activation time
        if not recieved_ns and self.start_time and time.time() - self.start_time > self.time_to_deactivate:
            self.start_time = time.time()
        

    def state_trigger(self):
        '''
        A function to determine whether or not the state machine needs to change states
        '''
        # if there is an action object present for long enough trigger the action object state
        if self.current_state != self.action_object:
            if self.action_object_start_time and time.time() - self.action_object_start_time >= self.time_to_activate and self.action_object_status == 'true':
                if self.current_state.id == 'blocked':
                    self.action_object_start_time = time.time()
                    return
                if self.current_state.id == 'clear':
                    self.clear_to_action_object()
                    self.action_object_start_time = time.time()
                    return
                if self.current_state.id == 'check':
                    self.check_to_action_object()
                    self.action_object_start_time = time.time()
                    return
                if self.current_state.id == 'gravel':
                    self.gravel_to_action_object()
                    self.action_object_start_time = time.time()
                    return
                elif self.current_state.id == 'out_of_state':
                    self.out_of_state_to_action_object()
                    self.action_object_start_time = time.time()
                    return
                return

        # if the current state is out of state, trigger a state based on the current status if it has been active long enough
        if self.candidate_count > 2:
            if self.current_state == self.out_of_state:
                if self.start_time and time.time() - self.start_time >= self.time_to_activate:
                    if self.current_status == 'blocked':
                        self.out_of_state_to_blocked()
                        return
                    if self.current_status == 'clear':
                        self.out_of_state_to_clear()
                        return
                    if self.current_status == 'check':
                        self.out_of_state_to_check()
                        return
                    if self.current_status == 'gravel':
                        self.out_of_state_to_gravel()
                        return

                return
        
        # state transition for the action object state if it has been inactive for too long
        if self.current_state == self.action_object and self.action_object_last_update_time:
            if self.action_object_start_time and time.time() - self.action_object_last_update_time > self.time_to_deactivate:
                if time.time() - self.start_time >= self.time_to_activate:
                    if self.current_status == 'blocked':
                        self.action_object_to_blocked()
                        return
                    if self.current_status == 'clear':
                        self.action_object_to_clear()
                        return
                    if self.current_status == 'check':
                        self.action_object_to_check()
                        return
                    if self.current_status == 'gravel':
                        self.action_object_to_gravel()
                        return
                    elif self.action_object_status == 'false':
                        self.action_object_to_out_of_state()
                        return
                else:
                    self.action_object_to_out_of_state()
                
                self.action_object_last_update_time = None
        else:
            if self.last_update_time and time.time() - self.last_update_time > self.time_to_deactivate:
                # state transition for the blocked state if it has been inactive for too long
                if self.current_state.id == 'blocked' and time.time() - self.action_object_start_time >= self.time_to_activate and self.action_object_status == 'true':
                    self.blocked_to_action_object()
                    return
                if self.current_state.id == 'blocked' and time.time() - self.start_time >= self.time_to_activate:
                    if self.current_status == 'clear' and self.candidate_count > 2:
                        self.blocked_to_clear()
                        return
                    if self.current_status == 'check' and self.candidate_count > 2:
                        self.blocked_to_check()
                        return
                    if self.current_status == 'gravel' and self.candidate_count > 2:
                        self.blocked_to_gravel()
                        return
                    elif not self.current_status:
                        self.blocked_to_out_of_state()
                        return
                elif self.current_state.id == 'blocked':
                    self.blocked_to_out_of_state()
                    return
                # state transition for the clear state if it has been inactive for too long
                if self.current_state.id == 'clear' and time.time() - self.action_object_start_time >= self.time_to_activate and self.action_object_status == 'true':
                    self.clear_to_action_object()
                    return
                if self.current_state.id == 'clear' and time.time() - self.start_time >= self.time_to_activate:
                    if self.current_status == 'blocked' and self.candidate_count > 2:
                        self.clear_to_blocked()
                        return                    
                    if self.current_status == 'check' and self.candidate_count > 2:
                        self.clear_to_check()
                        return
                    if self.current_status == 'gravel' and self.candidate_count > 2:
                        self.clear_to_gravel()
                        return
                    elif not self.current_status:
                        self.clear_to_out_of_state()
                        return
                elif self.current_state.id == 'clear':
                    self.clear_to_out_of_state()
                    return
                # state transition for the check state if it has been inactive for too long
                if self.current_state.id == 'check' and time.time() - self.action_object_start_time >= self.time_to_activate and self.action_object_status == 'true':
                    self.check_to_action_object()
                    return
                if self.current_state.id == 'check' and time.time() - self.start_time >= self.time_to_activate:
                    if self.current_status == 'blocked' and self.candidate_count > 2:
                        self.check_to_blocked()
                        return
                    if self.current_status == 'clear' and self.candidate_count > 2:
                        self.check_to_clear()
                        return
                    if self.current_status == 'gravel' and self.candidate_count > 2:
                        self.check_to_gravel()
                        return
                    elif not self.current_status:
                        self.check_to_out_of_state()
                        return
                elif self.current_state.id == 'check':
                    self.check_to_out_of_state()
                    self.last_update_time = None
                    return
                
                # state transition for the gravel state if it has been inactive for too long
                if self.current_state.id == 'check' and time.time() - self.action_object_start_time >= self.time_to_activate and self.action_object_status == 'true':
                    self.gravel_to_action_object()
                    return
                if self.current_state.id == 'gravel' and time.time() - self.start_time >= self.time_to_activate:
                    if self.current_status == 'blocked' and self.candidate_count > 2:
                        self.gravel_to_blocked()
                        return
                    if self.current_status == 'clear' and self.candidate_count > 2:
                        self.gravel_to_clear()
                        return
                    if self.current_status == 'check' and self.candidate_count > 2:
                        self.gravel_to_check()
                        return
                    elif not self.current_status:
                        self.gravel_to_out_of_state()
                        return
                elif self.current_state.id == 'gravel':
                    self.gravel_to_out_of_state()
                    self.last_update_time = None
                    return

    def step_down(self, target_fan_speed, target_nozzle_state):
        '''
        Function to gradually lower fan speed and change nozzle state
        Args:
            target_fan_speed: The target fan speed to step down to
            target_nozzle_state: The target nozzle state to set
        '''
        # Monitor the state that triggered the step down so it can stop if a state transition occurs
        self.trigger_state = self.current_state
        self.nozzle_state = target_nozzle_state
        
        # While the fan speed is greater than 1 and has not reached the target speed and the current state is still the trigger state
        while self.fan_speed > 1 and self.fan_speed != target_fan_speed and self.fan_speed > target_fan_speed:
            if self.current_state == self.trigger_state or self.current_state == self.out_of_state:
                print(f'stepping down from {self.fan_speed} to {target_fan_speed}')
                self.fan_speed -= 1
                time.sleep(self.stepdown_time)
        return

    def ramp_fan_then_open(self, target_fan_speed, target_nozzle_state):
        '''
        Function to raise the fanspeed before opening the nozzle
        '''
        self.trigger_state = self.current_state
        self.fan_speed = target_fan_speed
        time.sleep(0.5)
        self.nozzle_state = target_nozzle_state

    def get_nozzle_state(self):
        '''
        Function to return the current nozzle state
        Returns: self.nozzle_state
        '''
        return(self.nozzle_state)

    def get_fan_speed(self):
        return(self.fan_speed)
    
    def get_current_status(self):
        return(self.current_status)
    
    def get_current_state(self):
        return(self.current_state.id)

    def get_time_difference(self):
        if self.start_time:
            return(time.time() - self.start_time)
    
    def get_action_object_status(self):
        return(self.action_object_status)

    def get_action_object_difference(self):
        return(time.time() - self.action_object_start_time)     
        
    def on_enter_clear(self):
        #self.can_send(4, 0)
        #self.nozzle_state = 0
        #self.fan_speed = 4
        # Create a thread to step down the fan speed without blocking
        if self.fan_speed > 4:
            thread = threading.Thread(target=self.step_down, args=(4, 0))
            thread.start()
        else:
            self.nozzle_state = 0
            self.fan_speed = 4
        self.debug_print('#### entering clear state ####')
        self.start_time = time.time()
        self.last_update_time = time.time()
        self.candidate_count = 0
        return

    def on_exit_clear(self):
        pass

    def on_enter_action_object(self):
        if self.nozzle_state == 0:
            thread = threading.Thread(target=self.ramp_fan_then_open, args=(8, 1))
            thread.start()
        else:
            self.nozzle_state = 1
            self.fan_speed = 8
        self.debug_print('#### entering action object state ####')
        self.action_object_start_time = time.time()
        self.action_object_last_update_time = time.time()
        self.candidate_count = 0
        return
    
    def on_exit_action_object(self):
        pass

    def on_enter_blocked(self):
        if self.nozzle_state == 0:
            thread = threading.Thread(target=self.ramp_fan_then_open, args=(8, 1))
            thread.start()
        else:
            self.nozzle_state = 1
            self.fan_speed = 8
        self.debug_print('#### entering blocked state ####')
        self.start_time = time.time()
        self.last_update_time = time.time()
        self.candidate_count = 0
        return

    def on_exit_blocked(self):
        pass

    def on_enter_check(self):
        #self.can_send(1, 0)
        #self.nozzle_state = 0
        #self.fan_speed = 1
        self.debug_print('#### entering check state ####')
        self.start_time = time.time()
        self.last_update_time = time.time()
        self.candidate_count = 0
        return

    def on_exit_check(self):
        pass

    def on_enter_out_of_state(self):
        self.debug_print('#### Returning to out of state ####')
        self.start_time = time.time()
        self.last_update_time = None
        self.candidate_count = 0
        return

    def on_exit_out_of_state(self):
        pass

    def on_enter_gravel(self):
        self.nozzle_state = 0
        self.fan_speed = 7
        self.debug_print('#### entering gravel state ####')
        self.start_time = time.time()
        self.last_update_time = time.time()
        self.candidate_count = 0
        return
    
    def on_exit_gravel(self):
        pass

