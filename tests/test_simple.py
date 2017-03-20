"""Contain the tests for proxy device server."""

# Imports
import time
from collections import defaultdict

from tango.server import command
from tango import DevState, AttrWriteType
from tango.test_context import DeviceTestContext

# Proxy imports
from facadedevice.graph import VALID, triplet
from facadedevice import Facade, TimedFacade, state_attribute
from facadedevice import local_attribute


def event_mock(mocker, cls):
    change = defaultdict(mocker.Mock)
    archive = defaultdict(mocker.Mock)
    cls.push_change_event = mocker.Mock(
        side_effect=lambda key, *args, **kwargs: change[key](*args, **kwargs))
    cls.push_archive_event = mocker.Mock(
        side_effect=lambda key, *args, **kwargs: archive[key](*args, **kwargs))
    return change, archive


def test_empty_device(mocker):

    class Test(Facade):
        pass

    time.time
    mocker.patch('time.time').return_value = 1.0
    change_events, archive_events = event_mock(mocker, Test)

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
    change_events, archive_events = event_mock(mocker, Test)

    with DeviceTestContext(Test, debug=3) as proxy:
        assert proxy.state() == DevState.ON
        assert proxy.status() == "It's 1.0 o'clock!"
        expected_state = DevState.ON, 1.0, VALID
        expected_status = "It's 1.0 o'clock!", 1.0, VALID
        change_events['State'].assert_called_with(*expected_state)
        archive_events['State'].assert_called_with(*expected_state)
        change_events['Status'].assert_called_with(*expected_status)
        archive_events['Status'].assert_called_with(*expected_status)


def test_simple_device_no_status(mocker):

    class Test(TimedFacade):

        @state_attribute(bind=['Time'])
        def State(self, time):
            return DevState.ON

    time.time
    mocker.patch('time.time').return_value = 1.0
    change_events, archive_events = event_mock(mocker, Test)

    with DeviceTestContext(Test, debug=3) as proxy:
        assert proxy.state() == DevState.ON
        assert proxy.status() == "The device is in ON state."
        expected_state = DevState.ON, 1.0, VALID
        expected_status = "The device is in ON state.", 1.0, VALID
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
    change_events, archive_events = event_mock(mocker, Test)
    expected_status = "Exception while updating node <State>:\n"
    expected_status += "  RuntimeError('Ooops',)"

    with DeviceTestContext(Test) as proxy:
        assert proxy.state() == DevState.FAULT
        assert proxy.status() == expected_status
        expected_state = DevState.FAULT, 1.0, VALID
        expected_status = expected_status, 1.0, VALID
        change_events['State'].assert_called_with(*expected_state)
        archive_events['State'].assert_called_with(*expected_state)
        change_events['Status'].assert_called_with(*expected_status)
        archive_events['Status'].assert_called_with(*expected_status)


def test_empty_state(mocker):

    class Test(TimedFacade):

        A = local_attribute(
            dtype=float,
            access=AttrWriteType.READ_WRITE)

        @state_attribute(bind=['A'])
        def State(self, a):
            return DevState.ON, str(a)

        @command
        def reset(self):
            self.graph['A'].set_result(None)

    time.time
    mocker.patch('time.time').return_value = 1.0
    change_events, archive_events = event_mock(mocker, Test)

    with DeviceTestContext(Test) as proxy:
        assert proxy.state() == DevState.UNKNOWN
        proxy.A = 2
        assert proxy.state() == DevState.ON
        assert proxy.status() == "2.0"
        proxy.reset()
        assert proxy.state() == DevState.UNKNOWN
        assert proxy.status() == "The state is currently not available."


def test_delete_device():

    class Test(Facade):

        def init_device(self):
            super(Test, self).init_device()
            self.delete_device()
            self.set_state(DevState.ON)

    with DeviceTestContext(Test) as proxy:
        assert proxy.state() == DevState.ON


def test_delete_device_fail():

    class Test(Facade):

        def init_device(self):
            super(Test, self).init_device()
            self._graph = None
            self.delete_device()
            self.set_state(DevState.ON)

    with DeviceTestContext(Test) as proxy:
        assert proxy.state() == DevState.ON
        info = proxy.getinfo()
        assert 'Error while resetting the graph' in info


def test_manual_state(mocker):

    class Test(TimedFacade):

        State = state_attribute()

        @command
        def On(self):
            result = triplet(DevState.ON, time.time())
            self.graph['State'].set_result(result)

    time.time
    mocker.patch('time.time').return_value = 1.0
    change_events, archive_events = event_mock(mocker, Test)

    with DeviceTestContext(Test, debug=3) as proxy:
        assert proxy.state() == DevState.UNKNOWN
        assert proxy.status() == "The device is in UNKNOWN state."
        proxy.On()
        assert proxy.state() == DevState.ON
        assert proxy.status() == "The device is in ON state."
        expected_state = DevState.ON, 1.0, VALID
        expected_status = "The device is in ON state.", 1.0, VALID
        change_events['State'].assert_called_with(*expected_state)
        archive_events['State'].assert_called_with(*expected_state)
        change_events['Status'].assert_called_with(*expected_status)
        archive_events['Status'].assert_called_with(*expected_status)
