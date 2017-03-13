"""Contain the tests for proxy device server."""

# Imports
from mock import Mock

from tango.test_context import DeviceTestContext
from tango import DevState, EventType, EventData, AttrQuality

# Proxy imports
from facadedevice import Facade, proxy_attribute, common

# Local imports
from test_simple import event_mock


def test_ro_proxy_attribute():

    class Test(Facade):

        attr = proxy_attribute(
            dtype=float,
            prop='prop')

    change_events, archive_events = event_mock(Test)
    common.create_device_proxy = Mock()
    inner_proxy = common.create_device_proxy.return_value
    inner_proxy.dev_name.return_value = 'a/b/c'
    subscribe_event = inner_proxy.subscribe_event

    with DeviceTestContext(Test, debug=5, properties={'prop': 'a/b/c/d'}) as proxy:
        # Device not in fault
        assert proxy.state() == DevState.UNKNOWN
        # Check mocks
        common.create_device_proxy.assert_called_with('a/b/c')
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
