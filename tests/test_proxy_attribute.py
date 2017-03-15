"""Contain the tests for proxy device server."""

# Imports
from mock import Mock

from tango.test_context import DeviceTestContext
from tango import DevState, EventType, EventData, AttrQuality
from tango import AttrWriteType

# Proxy imports
from facadedevice import Facade, proxy_attribute, utils, device

# Local imports
from test_simple import event_mock


def test_proxy_attribute(mocker):

    class Test(Facade):

        attr = proxy_attribute(
            dtype=float,
            prop='prop')

    change_events, archive_events = event_mock(Test)

    mocker.patch('facadedevice.utils.create_device_proxy')
    inner_proxy = utils.create_device_proxy.return_value
    inner_proxy.dev_name.return_value = 'a/b/c'
    subscribe_event = inner_proxy.subscribe_event

    with DeviceTestContext(Test, properties={'prop': 'a/b/c/d'}) as proxy:
        # Device not in fault
        assert proxy.state() == DevState.UNKNOWN
        # Check mocks
        utils.create_device_proxy.assert_called_with('a/b/c')
        subscribe_event.assert_called()
        cb = subscribe_event.call_args[0][2]
        args = 'd', EventType.CHANGE_EVENT, cb, [], False
        subscribe_event.assert_called_with(*args)
        # No event pushed
        change_events['attr'].assert_not_called
        archive_events['attr'].assert_not_called
        # Trigger events
        event = Mock(spec=EventData)
        event.attr_name = 'a/b/c/d'
        event.errors = False
        event.attr_value.value = 1.2
        event.attr_value.time.totime.return_value = 3.4
        event.attr_value.quality = AttrQuality.ATTR_ALARM
        cb(event)
        # Device not in fault
        assert proxy.state() == DevState.UNKNOWN
        # Check events
        expected = 1.2, 3.4, AttrQuality.ATTR_ALARM
        change_events['attr'].assert_called_with(*expected)
        archive_events['attr'].assert_called_with(*expected)


def test_proxy_attribute_with_convertion(mocker):

    class Test(Facade):

        @proxy_attribute(
            dtype=float,
            prop='prop')
        def attr(self, raw):
            return raw*10

    change_events, archive_events = event_mock(Test)

    mocker.patch('facadedevice.utils.create_device_proxy')
    inner_proxy = utils.create_device_proxy.return_value
    inner_proxy.dev_name.return_value = 'a/b/c'
    subscribe_event = inner_proxy.subscribe_event

    with DeviceTestContext(Test, properties={'prop': 'a/b/c/d'}) as proxy:
        # Device not in fault
        assert proxy.state() == DevState.UNKNOWN
        # Check mocks
        utils.create_device_proxy.assert_called_with('a/b/c')
        subscribe_event.assert_called()
        cb = subscribe_event.call_args[0][2]
        args = 'd', EventType.CHANGE_EVENT, cb, [], False
        subscribe_event.assert_called_with(*args)
        # No event pushed
        change_events['attr'].assert_not_called
        archive_events['attr'].assert_not_called
        # Trigger events
        event = Mock(spec=EventData)
        event.attr_name = 'a/b/c/d'
        event.errors = False
        event.attr_value.value = 1.2
        event.attr_value.time.totime.return_value = 3.4
        event.attr_value.quality = AttrQuality.ATTR_ALARM
        cb(event)
        # Device not in fault
        assert proxy.state() == DevState.UNKNOWN
        # Check events
        expected = 12., 3.4, AttrQuality.ATTR_ALARM
        change_events['attr'].assert_called_with(*expected)
        archive_events['attr'].assert_called_with(*expected)


def test_writable_proxy_attribute(mocker):

    class Test(Facade):

        attr = proxy_attribute(
            dtype=float,
            prop='prop',
            access=AttrWriteType.READ_WRITE)

    change_events, archive_events = event_mock(Test)

    mocker.patch('facadedevice.utils.create_device_proxy')
    inner_proxy = utils.create_device_proxy.return_value
    inner_proxy.dev_name.return_value = 'a/b/c'
    subscribe_event = inner_proxy.subscribe_event

    mocker.patch('facadedevice.device.AttributeProxy')
    inner_attr_proxy = device.AttributeProxy.return_value

    with DeviceTestContext(Test, properties={'prop': 'a/b/c/d'}) as proxy:
        # Device not in fault
        assert proxy.state() == DevState.UNKNOWN
        # Check mocks
        utils.create_device_proxy.assert_called_with('a/b/c')
        subscribe_event.assert_called()
        cb = subscribe_event.call_args[0][2]
        args = 'd', EventType.CHANGE_EVENT, cb, [], False
        subscribe_event.assert_called_with(*args)
        # No event pushed
        change_events['attr'].assert_not_called
        archive_events['attr'].assert_not_called
        # Trigger events
        event = Mock(spec=EventData)
        event.attr_name = 'a/b/c/d'
        event.errors = False
        event.attr_value.value = 1.2
        event.attr_value.time.totime.return_value = 3.4
        event.attr_value.quality = AttrQuality.ATTR_ALARM
        cb(event)
        # Device not in fault
        assert proxy.state() == DevState.UNKNOWN
        # Check events
        expected = 1.2, 3.4, AttrQuality.ATTR_ALARM
        change_events['attr'].assert_called_with(*expected)
        archive_events['attr'].assert_called_with(*expected)
        # Test write
        proxy.write_attribute('attr', 32.)
        device.AttributeProxy.assert_called_with('a/b/c/d')
        inner_attr_proxy.write_attribute.called_with(32.)
