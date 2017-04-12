"""Contain the tests for proxy device server."""

# Imports
import time
import pytest

from tango.server import command
from tango.test_context import DeviceTestContext
from tango import AttrQuality, DevState
from tango import AttrWriteType, DevFailed

# Proxy imports
from facadedevice import Facade, triplet
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


def test_local_attribute_non_exposed(mocker):

    class Test(Facade):

        A = local_attribute(
            create_attribute=False)

        @A.notify
        def on_a(self, node):
            on_a_mock(*node.result())

        @command(dtype_in=float)
        def set_a(self, value):
            result = triplet(value, time.time())
            self.graph['A'].set_result(result)

    mocker.patch('time.time').return_value = 1.0

    on_a_mock = mocker.Mock()

    with DeviceTestContext(Test) as proxy:
        # Test
        assert proxy.state() == DevState.UNKNOWN
        with pytest.raises(AttributeError):
            proxy.A
        proxy.set_a(21)
        # Check callback
        expected = 21, 1.0, AttrQuality.ATTR_VALID
        on_a_mock.assert_called_once_with(*expected)


def test_invalid_local_attribute(mocker):

    with pytest.raises(ValueError) as context:

        class Test(Facade):

            A = local_attribute(
                dtype=float,
                create_attribute=False)

    assert 'Attribute creation is disabled' in str(context.value)


def test_local_attribute_with_default_value(mocker):

    class Test(Facade):

        @local_attribute(
            dtype=float,
            access=AttrWriteType.READ_WRITE)
        def A(self):
            return 3.14

        @A.notify
        def on_a(self, node):
            on_a_mock(*node.result())

    change_events, archive_events = event_mock(mocker, Test)

    time.time
    mocker.patch('time.time').return_value = 1.0

    on_a_mock = mocker.Mock()

    with DeviceTestContext(Test) as proxy:
        # First test
        assert proxy.state() == DevState.UNKNOWN
        assert proxy.A == 3.14
        # Check events
        expected = 3.14, 1.0, AttrQuality.ATTR_VALID
        change_events['A'].assert_called_once_with(*expected)
        archive_events['A'].assert_called_once_with(*expected)
        # Check callback
        on_a_mock.assert_called_once_with(*expected)
        # Reset
        on_a_mock.reset_mock()
        change_events['A'].reset_mock()
        archive_events['A'].reset_mock()
        # Second test
        proxy.A = 21
        assert proxy.A == 21
        # Check events
        expected = 21, 1.0, AttrQuality.ATTR_VALID
        change_events['A'].assert_called_once_with(*expected)
        archive_events['A'].assert_called_once_with(*expected)
        # Check callback
        on_a_mock.assert_called_once_with(*expected)


def test_local_attribute_with_default_exception(mocker):

    class Test(Facade):

        @local_attribute(
            dtype=float,
            access=AttrWriteType.READ_WRITE)
        def A(self):
            raise RuntimeError('Ooops')

        @A.notify
        def on_a(self, node):
            on_a_mock(*node.result())

    change_events, archive_events = event_mock(mocker, Test)

    time.time
    mocker.patch('time.time').return_value = 1.0

    on_a_mock = mocker.Mock()

    with DeviceTestContext(Test) as proxy:
        # First test
        assert proxy.state() == DevState.UNKNOWN
        with pytest.raises(DevFailed) as ctx:
            assert proxy.A
        assert 'Ooops' in str(ctx.value)
        # Check callback
        assert not on_a_mock.called
        # Reset
        on_a_mock.reset_mock()
        change_events['A'].reset_mock()
        archive_events['A'].reset_mock()
        # Second test
        proxy.A = 21
        assert proxy.A == 21
        # Check events
        expected = 21, 1.0, AttrQuality.ATTR_VALID
        change_events['A'].assert_called_once_with(*expected)
        archive_events['A'].assert_called_once_with(*expected)
        # Check callback
        on_a_mock.assert_called_once_with(*expected)
