"""Contain the tests for proxy device server."""

# Imports
import time
import pytest

from tango.server import command
from tango.test_context import DeviceTestContext
from tango import AttrQuality, DevState
from tango import AttrWriteType, DevFailed

# Proxy imports
from facadedevice import Facade
from facadedevice import local_attribute

# Local imports
from test_simple import event_mock


def test_local_attribute(mocker):

    class Test(Facade):

        A = local_attribute(
            dtype=float,
            access=AttrWriteType.READ_WRITE)

        @A.notify
        def on_a(self, node):
            on_a_mock(*node.result())

    change_events, archive_events = event_mock(mocker, Test)

    time.time
    mocker.patch('time.time').return_value = 1.0

    on_a_mock = mocker.Mock()

    with DeviceTestContext(Test) as proxy:
        # Test
        assert proxy.state() == DevState.UNKNOWN
        with pytest.raises(DevFailed):
            proxy.A
        proxy.A = 21
        assert proxy.A == 21
        # Check events
        expected = 21, 1.0, AttrQuality.ATTR_VALID
        change_events['A'].assert_called_once_with(*expected)
        archive_events['A'].assert_called_once_with(*expected)
        # Check callback
        on_a_mock.assert_called_once_with(*expected)


def test_local_attribute_callback_error(mocker):

    class Test(Facade):

        A = local_attribute(
            dtype=float,
            access=AttrWriteType.READ_WRITE)

        @A.notify
        def on_a(self, node):
            raise RuntimeError('Ooops')

    change_events, archive_events = event_mock(mocker, Test)
    mocker.patch('time.time').return_value = 1.0

    with DeviceTestContext(Test) as proxy:
        # Test
        assert proxy.state() == DevState.UNKNOWN
        with pytest.raises(DevFailed):
            proxy.A
        proxy.A = 21
        assert proxy.A == 21
        # Check events
        info = proxy.getinfo()
        print(info)
        assert "Exception while running user callback for node <A>:" in info
        assert "  Ooops" in info


def test_local_attribute_empty_push(mocker):

    class Test(Facade):

        A = local_attribute(
            dtype=float,
            access=AttrWriteType.READ_WRITE)

        @command
        def reset(self):
            self.graph['A'].set_result(None)

    change_events, archive_events = event_mock(mocker, Test)
    mocker.patch('time.time').return_value = 1.0

    with DeviceTestContext(Test) as proxy:
        # Test
        assert proxy.state() == DevState.UNKNOWN
        proxy.A = 21
        assert proxy.A == 21
        change_events['A'].reset_mock()
        archive_events['A'].reset_mock()
        # Reset
        proxy.reset()
        with pytest.raises(DevFailed):
            proxy.A
        # Check events
        assert not change_events['A'].called
        assert not archive_events['A'].called
        info = proxy.getinfo()
        assert "No errors in history" in info
