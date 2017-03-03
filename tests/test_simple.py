"""Contain the tests for proxy device server."""

# Imports
from mock import Mock
from collections import defaultdict

from tango import DevState
from tango.test_context import DeviceTestContext

# Proxy imports
from facadedevice import Facade


def event_mock(cls):
    change = defaultdict(Mock)
    archive = defaultdict(Mock)
    cls.push_change_event = Mock(
        side_effect=lambda key, *args, **kwargs: change[key](*args, **kwargs))
    cls.push_archive_event = Mock(
        side_effect=lambda key, *args, **kwargs: archive[key](*args, **kwargs))
    return change, archive


def test_empty_device():

    class Test(Facade):
        pass

    change_events, archive_events = event_mock(Test)

    with DeviceTestContext(Test) as proxy:
        assert proxy.state() == DevState.INIT
        assert proxy.status() == "The device is in INIT state."
        change_events['State'].assert_called_with(DevState.INIT)
        archive_events['State'].assert_called_with(DevState.INIT)


def test_simple_device():

    class Test(Facade):

        def state_from_data(self, data):
            return DevState.ON

        def status_from_data(self, data):
            return "It's ON!"

    change_events, archive_events = event_mock(Test)

    with DeviceTestContext(Test) as proxy:
        assert proxy.state() == DevState.ON
        assert proxy.status() == "It's ON!"
        change_events['State'].assert_called_with(DevState.ON)
        archive_events['State'].assert_called_with(DevState.ON)
        change_events['Status'].assert_called_with("It's ON!")
        archive_events['Status'].assert_called_with("It's ON!")


def test_state_error():

    class Test(Facade):

        def state_from_data(self, data):
            raise RuntimeError('Oooops')

    change_events, archive_events = event_mock(Test)
    expected_status = "Error while getting the device state.\nOooops"

    with DeviceTestContext(Test) as proxy:
        assert proxy.state() == DevState.FAULT
        assert proxy.status() == expected_status
        change_events['State'].assert_called_with(DevState.FAULT)
        archive_events['State'].assert_called_with(DevState.FAULT)
        change_events['Status'].assert_called_with(expected_status)
        archive_events['Status'].assert_called_with(expected_status)


def test_status_error():

    class Test(Facade):

        def state_from_data(self, data):
            return DevState.ON

        def status_from_data(self, data):
            raise RuntimeError('Oooops')

    change_events, archive_events = event_mock(Test)
    expected_status = "Error while getting the device status.\nOooops"

    with DeviceTestContext(Test) as proxy:
        assert proxy.state() == DevState.ON
        assert proxy.status() == expected_status
        change_events['State'].assert_called_with(DevState.ON)
        archive_events['State'].assert_called_with(DevState.ON)
        change_events['Status'].assert_called_with(expected_status)
        archive_events['Status'].assert_called_with(expected_status)
