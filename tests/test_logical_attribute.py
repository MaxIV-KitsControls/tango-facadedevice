"""Contain the tests for proxy device server."""

# Imports
import time
import pytest

from tango.test_context import DeviceTestContext
from tango import AttrQuality
from tango import AttrWriteType, DevFailed

# Proxy imports
from facadedevice import Facade
from facadedevice import local_attribute, logical_attribute

# Local imports
from test_simple import event_mock


def test_logical_attribute(mocker):

    class Test(Facade):

        @logical_attribute(
            dtype=float,
            bind=['A', 'B'])
        def C(self, a, b):
            return a/b

        A = local_attribute(
            dtype=float,
            access=AttrWriteType.READ_WRITE)

        B = local_attribute(
            dtype=float,
            access=AttrWriteType.READ_WRITE)

    change_events, archive_events = event_mock(mocker, Test)
    mocker.patch('time.time').return_value = 1.0

    with DeviceTestContext(Test) as proxy:
        # Test 1
        with pytest.raises(DevFailed):
            proxy.A
        with pytest.raises(DevFailed):
            proxy.B
        with pytest.raises(DevFailed):
            proxy.C
        # Test 2
        proxy.A = 21
        assert proxy.A == 21
        with pytest.raises(DevFailed):
            proxy.C
        # Test 3
        proxy.B = 7
        assert proxy.B == 7
        assert proxy.C == 3
        # Check events
        expected = 3.0, 1.0, AttrQuality.ATTR_VALID
        change_events['C'].assert_called_with(*expected)
        archive_events['C'].assert_called_with(*expected)


def test_diamond_attribute(mocker):

    class Test(Facade):

        A = local_attribute(
            dtype=float,
            access=AttrWriteType.READ_WRITE)

        @logical_attribute(
            dtype=float,
            bind=['A'])
        def B(self, a):
            return a*10

        @logical_attribute(
            dtype=float,
            bind=['A'])
        def C(self, a):
            return a*100

        @logical_attribute(
            dtype=float,
            bind=['A', 'B', 'C'])
        def D(self, a, b, c):
            return a + b + c

    change_events, archive_events = event_mock(mocker, Test)
    mocker.patch('time.time').return_value = 1.0

    with DeviceTestContext(Test) as proxy:
        # Test 1
        with pytest.raises(DevFailed):
            proxy.A
        with pytest.raises(DevFailed):
            proxy.B
        with pytest.raises(DevFailed):
            proxy.C
        with pytest.raises(DevFailed):
            proxy.D
        # Test 2
        proxy.A = 7
        assert proxy.A == 7
        assert proxy.B == 70
        assert proxy.C == 700
        assert proxy.D == 777
        # Check events
        expected = 777., 1.0, AttrQuality.ATTR_VALID
        change_events['D'].assert_called_once_with(*expected)
        archive_events['D'].assert_called_once_with(*expected)
