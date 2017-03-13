"""Contain the tests for proxy device server."""

# Imports
import time  # noqa
from mock import Mock
from collections import defaultdict

from tango import DevState
from tango.test_context import DeviceTestContext

# Proxy imports
from facadedevice.base import VALID
from facadedevice import Facade, TimedFacade, state_attribute


def event_mock(cls):
    change = defaultdict(Mock)
    archive = defaultdict(Mock)
    cls.push_change_event = Mock(
        side_effect=lambda key, *args, **kwargs: change[key](*args, **kwargs))
    cls.push_archive_event = Mock(
        side_effect=lambda key, *args, **kwargs: archive[key](*args, **kwargs))
    return change, archive


def test_empty_device(mocker):

    class Test(Facade):
        pass

    time.time
    mocker.patch('time.time').return_value = 1.0
    change_events, archive_events = event_mock(Test)

    with DeviceTestContext(Test) as proxy:
        assert proxy.state() == DevState.UNKNOWN
        assert proxy.status() == "The device is in UNKNOWN state."
        expected = DevState.UNKNOWN, 1.0, VALID
        change_events['State'].assert_called_with(*expected)
        archive_events['State'].assert_called_with(*expected)


def test_simple_device(mocker):

    class Test(TimedFacade):

        @state_attribute(bind=['Time'])
        def State(self, time):
            return DevState.ON, "It's {} o'clock!".format(time)

    time.time
    mocker.patch('time.time').return_value = 1.0
    change_events, archive_events = event_mock(Test)

    with DeviceTestContext(Test, debug=3) as proxy:
        assert proxy.state() == DevState.ON
        assert proxy.status() == "It's 1.0 o'clock!"
        expected_state = DevState.ON, 1.0, VALID
        expected_status = "It's 1.0 o'clock!", 1.0, VALID
        change_events['State'].assert_called_with(*expected_state)
        archive_events['State'].assert_called_with(*expected_state)
        change_events['Status'].assert_called_with(*expected_status)
        archive_events['Status'].assert_called_with(*expected_status)


def test_state_error(mocker):

    class Test(TimedFacade):

        @state_attribute(bind=['Time'])
        def State(self, time):
            raise RuntimeError('Ooops')

    time.time
    mocker.patch('time.time').return_value = 1.0
    change_events, archive_events = event_mock(Test)
    expected_status = "Error: RuntimeError('Ooops',)"

    with DeviceTestContext(Test) as proxy:
        assert proxy.state() == DevState.FAULT
        assert proxy.status() == expected_status
        expected_state = DevState.FAULT, 1.0, VALID
        expected_status = expected_status, 1.0, VALID
        change_events['State'].assert_called_with(*expected_state)
        archive_events['State'].assert_called_with(*expected_state)
        change_events['Status'].assert_called_with(*expected_status)
        archive_events['Status'].assert_called_with(*expected_status)
