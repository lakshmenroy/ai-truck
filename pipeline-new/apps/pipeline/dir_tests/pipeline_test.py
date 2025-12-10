"""
Unit tests for pipeline components
"""
import pytest
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from detection_categories import DETECTION_CATEGORIES
from can.state_machine import SmartStateMachine


def test_detection_categories():
    """Test detection category enum"""
    assert DETECTION_CATEGORIES.PGIE_CLASS_ID_BACKGROUND.value == 0
    assert DETECTION_CATEGORIES.PGIE_CLASS_ID_NOZZLE_CLEAR.value == 5
    assert DETECTION_CATEGORIES.PGIE_CLASS_ID_NOZZLE_BLOCKED.value == 4


def test_state_machine_initialization():
    """Test state machine initialization"""
    sm = SmartStateMachine()
    assert sm.nozzle_state == 0
    assert sm.fan_speed == 0
    assert sm.current_state == 'IDLE'


def test_state_machine_clear():
    """Test state machine with clear nozzle"""
    sm = SmartStateMachine()
    sm.status_send(recieved_ns='clear')
    
    assert sm.nozzle_state == 1
    assert sm.current_state == 'NOZZLE_CLEAR'
    assert sm.fan_speed == 2  # Low speed


def test_state_machine_blocked():
    """Test state machine with blocked nozzle"""
    sm = SmartStateMachine()
    sm.status_send(recieved_ns='blocked')
    
    assert sm.nozzle_state == 2
    assert sm.current_state == 'NOZZLE_BLOCKED'
    assert sm.fan_speed == 8  # High speed


def test_state_machine_check():
    """Test state machine with check nozzle"""
    sm = SmartStateMachine()
    sm.status_send(recieved_ns='check')
    
    assert sm.nozzle_state == 3
    assert sm.current_state == 'NOZZLE_CHECK'
    assert sm.fan_speed == 5  # Medium speed


def test_state_machine_gravel():
    """Test state machine with gravel detection"""
    sm = SmartStateMachine()
    sm.status_send(recieved_ns='gravel')
    
    assert sm.nozzle_state == 4
    assert sm.current_state == 'GRAVEL_DETECTED'


def test_state_machine_action_object():
    """Test state machine with action object"""
    sm = SmartStateMachine()
    sm.status_send(recieved_aos='true')
    
    assert sm.ao_status == 'true'


def test_state_machine_get_state_dict():
    """Test state machine dict export"""
    sm = SmartStateMachine()
    sm.status_send(recieved_ns='blocked', recieved_aos='true')
    
    state_dict = sm.get_state_dict()
    assert state_dict['nozzle_state'] == 2
    assert state_dict['fan_speed'] == 8
    assert state_dict['current_state'] == 'NOZZLE_BLOCKED'
    assert state_dict['ao_status'] == 'true'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])