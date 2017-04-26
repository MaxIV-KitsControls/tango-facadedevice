"""Contain the tests for proxy device server."""

# Imports
import pytest

# Tango imports
from tango.server import command
from tango.test_context import DeviceTestContext
from tango import DevState, EventType, EventData, AttrQuality
from tango import AttrWriteType, DevFailed

# Facade imports
from facadedevice import Facade, proxy_attribute, utils

# Local imports
from test_simple import event_mock


def test_proxy_attribute(mocker):

    class Test(Facade):

        attr = proxy_attribute(
            dtype=float,
            property_name='prop')

    change_events, archive_events = event_mock(mocker, Test)

    mocker.patch('facadedevice.utils.DeviceProxy')
    inner_proxy = utils.DeviceProxy.return_value
    inner_proxy.dev_name.return_value = 'a/b/c'
    subscribe_event = inner_proxy.subscribe_event

    with DeviceTestContext(Test, properties={'prop': 'a/b/c/d'}) as proxy:
        # Device not in fault
        assert proxy.state() == DevState.UNKNOWN
        # Check mocks
        utils.DeviceProxy.assert_called_with('a/b/c')
        assert subscribe_event.called
        cb = subscribe_event.call_args[0][2]
        args = 'd', EventType.CHANGE_EVENT, cb, [], False
        subscribe_event.assert_called_with(*args)
        # No event pushed
        change_events['attr'].assert_not_called()
        archive_events['attr'].assert_not_called()
        # Trigger events
        event = mocker.Mock(spec=EventData)
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
        # Check info
        info = proxy.getinfo()
        assert "- a/b/c/d (CHANGE_EVENT)" in info
        # Check delete + init device
        proxy.init()
        assert proxy.state() == DevState.UNKNOWN


def test_proxy_attribute_with_convertion(mocker):

    class Test(Facade):

        @proxy_attribute(
            dtype=float,
            property_name='prop')
        def attr(self, raw):
            return raw*10

    change_events, archive_events = event_mock(mocker, Test)

    mocker.patch('facadedevice.utils.DeviceProxy')
    inner_proxy = utils.DeviceProxy.return_value
    inner_proxy.dev_name.return_value = 'a/b/c'
    subscribe_event = inner_proxy.subscribe_event

    with DeviceTestContext(Test, properties={'prop': 'a/b/c/d'}) as proxy:
        # Device not in fault
        assert proxy.state() == DevState.UNKNOWN
        # Check mocks
        utils.DeviceProxy.assert_called_with('a/b/c')
        assert subscribe_event.called
        cb = subscribe_event.call_args[0][2]
        args = 'd', EventType.CHANGE_EVENT, cb, [], False
        subscribe_event.assert_called_with(*args)
        # No event pushed
        change_events['attr'].assert_not_called()
        archive_events['attr'].assert_not_called()
        # Trigger events
        event = mocker.Mock(spec=EventData)
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
            property_name='prop',
            access=AttrWriteType.READ_WRITE)

    change_events, archive_events = event_mock(mocker, Test)

    mocker.patch('facadedevice.utils.DeviceProxy')
    inner_proxy = utils.DeviceProxy.return_value
    inner_proxy.dev_name.return_value = 'a/b/c'
    subscribe_event = inner_proxy.subscribe_event

    with DeviceTestContext(Test, properties={'prop': 'a/b/c/d'}) as proxy:
        # Device not in fault
        assert proxy.state() == DevState.UNKNOWN
        # Check mocks
        utils.DeviceProxy.assert_called_with('a/b/c')
        assert subscribe_event.called
        cb = subscribe_event.call_args[0][2]
        args = 'd', EventType.CHANGE_EVENT, cb, [], False
        subscribe_event.assert_called_with(*args)
        # No event pushed
        change_events['attr'].assert_not_called()
        archive_events['attr'].assert_not_called()
        # Trigger events
        event = mocker.Mock(spec=EventData)
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
        utils.DeviceProxy.reset_mock()
        proxy.write_attribute('attr', 32.)
        inner_proxy.write_attribute.assert_called_with('d', 32.)


def test_proxy_attribute_with_periodic_event(mocker):

    class Test(Facade):

        attr = proxy_attribute(
            dtype=float,
            property_name='prop')

    def sub(attr, etype, *args):
        if etype != EventType.PERIODIC_EVENT:
            raise DevFailed('Nope')

    change_events, archive_events = event_mock(mocker, Test)

    mocker.patch('facadedevice.utils.DeviceProxy')
    inner_proxy = utils.DeviceProxy.return_value
    inner_proxy.dev_name.return_value = 'a/b/c'
    subscribe_event = inner_proxy.subscribe_event
    subscribe_event.side_effect = sub

    with DeviceTestContext(Test, properties={'prop': 'a/b/c/d'}) as proxy:
        # Device not in fault
        assert proxy.state() == DevState.UNKNOWN
        # Check mocks
        utils.DeviceProxy.assert_called_with('a/b/c')
        assert subscribe_event.called
        cb = subscribe_event.call_args[0][2]
        args = 'd', EventType.PERIODIC_EVENT, cb, [], False
        subscribe_event.assert_called_with(*args)
        # No event pushed
        change_events['attr'].assert_not_called()
        archive_events['attr'].assert_not_called()
        # Trigger events
        event = mocker.Mock(spec=EventData)
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


def test_proxy_attribute_not_evented(mocker):

    class Test(Facade):

        attr = proxy_attribute(
            dtype=float,
            property_name='prop')

    change_events, archive_events = event_mock(mocker, Test)

    mocker.patch('facadedevice.utils.DeviceProxy')
    inner_proxy = utils.DeviceProxy.return_value
    inner_proxy.dev_name.return_value = 'a/b/c'
    subscribe_event = inner_proxy.subscribe_event
    subscribe_event.side_effect = DevFailed

    with DeviceTestContext(Test, properties={'prop': 'a/b/c/d'}) as proxy:
        # Device in fault
        expected = "Exception while connecting proxy_attribute <attr>"
        assert proxy.state() == DevState.FAULT
        assert expected in proxy.status()
        # Check mocks
        utils.DeviceProxy.assert_called_with('a/b/c')
        assert subscribe_event.called
        cb = subscribe_event.call_args[0][2]
        args = 'd', EventType.PERIODIC_EVENT, cb, [], False
        subscribe_event.assert_called_with(*args)
        # No event pushed
        change_events['attr'].assert_not_called()
        archive_events['attr'].assert_not_called()


def test_proxy_attribute_with_wrong_events(mocker):

    class Test(Facade):

        attr = proxy_attribute(
            dtype=float,
            property_name='prop')

    change_events, archive_events = event_mock(mocker, Test)

    mocker.patch('facadedevice.utils.DeviceProxy')
    inner_proxy = utils.DeviceProxy.return_value
    inner_proxy.dev_name.return_value = 'a/b/c'
    subscribe_event = inner_proxy.subscribe_event

    with DeviceTestContext(Test, properties={'prop': 'a/b/c/d'}) as proxy:
        # Device not in fault
        assert proxy.state() == DevState.UNKNOWN
        # Check mocks
        utils.DeviceProxy.assert_called_with('a/b/c')
        assert subscribe_event.called
        cb = subscribe_event.call_args[0][2]
        args = 'd', EventType.CHANGE_EVENT, cb, [], False
        subscribe_event.assert_called_with(*args)
        # No event pushed
        change_events['attr'].assert_not_called()
        archive_events['attr'].assert_not_called()
        # Invalid event
        cb("Not an event")
        assert proxy.state() == DevState.UNKNOWN
        change_events['attr'].assert_not_called()
        archive_events['attr'].assert_not_called()
        # Ignore event
        event = mocker.Mock(spec=EventData)
        event.attr_name = 'a/b/c/d'
        exception = RuntimeError('Ooops')
        exception.reason = 'API_PollThreadOutOfSync'
        event.errors = [exception, RuntimeError()]
        cb(event)
        assert proxy.state() == DevState.UNKNOWN
        change_events['attr'].assert_not_called()
        archive_events['attr'].assert_not_called()
        # Check info
        info = proxy.getinfo()
        assert "Received an event from a/b/c/d that contains errors" in info
        assert "Ooops" in info
        # Error event
        event = mocker.Mock(spec=EventData)
        event.attr_name = 'a/b/c/d'
        exception = RuntimeError('Ooops')
        exception.reason = 'ValidReason'
        event.errors = [exception, RuntimeError()]
        cb(event)
        assert proxy.state() == DevState.UNKNOWN
        for dct in (change_events, archive_events):
            lst = dct['attr'].call_args_list
            assert len(lst) == 1
            exc, = lst[0][0]
            assert isinstance(exc, DevFailed)
            assert 'Ooops' in exc.args[0].desc
        # Check info
        info = proxy.getinfo()
        assert "Raised 2 times" in info


def test_disabled_proxy_attribute(mocker):

    class Test(Facade):

        attr = proxy_attribute(
            dtype=float,
            property_name='prop',
            access=AttrWriteType.READ_WRITE)

    change_events, archive_events = event_mock(mocker, Test)
    device_proxy = mocker.patch('facadedevice.utils.DeviceProxy')

    with DeviceTestContext(Test, properties={'prop': 'None'}) as proxy:
        # Device not in fault
        assert proxy.state() == DevState.UNKNOWN
        # Check mocks
        assert not device_proxy.called
        # Test write
        assert proxy.attr is None


def test_emulated_proxy_attribute(mocker):

    class Test(Facade):

        attr = proxy_attribute(
            dtype=float,
            property_name='prop',
            access=AttrWriteType.READ_WRITE)

    change_events, archive_events = event_mock(mocker, Test)
    device_proxy = mocker.patch('facadedevice.utils.DeviceProxy')

    with DeviceTestContext(Test, properties={'prop': '0.5'}) as proxy:
        # Device not in fault
        assert proxy.state() == DevState.UNKNOWN
        # Check mocks
        assert not device_proxy.called
        # Test write
        assert proxy.attr == 0.5
        proxy.attr += 1
        assert proxy.attr == 1.5


def test_non_writable_proxy_attribute(mocker):

    class Test(Facade):

        attr = proxy_attribute(
            dtype=float,
            property_name='prop',
            access=AttrWriteType.READ_WRITE)

    change_events, archive_events = event_mock(mocker, Test)

    mocker.patch('facadedevice.utils.DeviceProxy')
    inner_proxy = utils.DeviceProxy.return_value
    config = mocker.Mock(writable=AttrWriteType.READ)
    inner_proxy.get_attribute_config.return_value = config
    inner_proxy.dev_name.return_value = 'a/b/c'

    with DeviceTestContext(Test, properties={'prop': 'a/b/c/d'}) as proxy:
        assert proxy.state() == DevState.FAULT
        assert "The attribute a/b/c/d is not writable" in proxy.status()


def test_missing_property():

    class Test(Facade):

        attr = proxy_attribute(
            dtype=float,
            property_name='prop',
            access=AttrWriteType.READ_WRITE)

    with DeviceTestContext(Test) as proxy:
        assert proxy.state() == DevState.FAULT
        assert "Missing property: prop" in proxy.status()
        assert "The device is currently stopped" in proxy.getinfo()
        assert "Missing property: prop" in proxy.getinfo()


def test_empty_property():

    class Test(Facade):

        attr = proxy_attribute(
            dtype=float,
            property_name='prop',
            access=AttrWriteType.READ_WRITE)

    with DeviceTestContext(Test, properties={'prop': ''}) as proxy:
        assert proxy.state() == DevState.FAULT
        assert "Property 'prop' is empty" in proxy.status()
        assert "The device is currently stopped" in proxy.getinfo()
        assert "Property 'prop' is empty" in proxy.getinfo()


def test_proxy_attribute_broken_internals(mocker):

    class Test(Facade):

        attr = proxy_attribute(
            dtype=float,
            property_name='prop')

        @command
        def break_device(self):
            del self._event_dict

    change_events, archive_events = event_mock(mocker, Test)

    mocker.patch('facadedevice.utils.DeviceProxy')
    inner_proxy = utils.DeviceProxy.return_value
    inner_proxy.dev_name.return_value = 'a/b/c'

    with DeviceTestContext(Test, properties={'prop': 'a/b/c/d'}) as proxy:
        # Device not in fault
        assert proxy.state() == DevState.UNKNOWN
        # Break internal state
        proxy.break_device()
        # Run delete device
        proxy.init()
        # State is OK
        assert proxy.state() == DevState.UNKNOWN


def test_proxy_attribute_broken_unsubscription(mocker):

    class Test(Facade):

        attr = proxy_attribute(
            dtype=float,
            property_name='prop')

        @command
        def delete(self):
            self.delete_device()

    mocker.patch('facadedevice.utils.DeviceProxy')
    inner_proxy = utils.DeviceProxy.return_value
    inner_proxy.dev_name.return_value = 'a/b/c'

    inner_proxy.unsubscribe_event.side_effect = RuntimeError("Ooops")

    with DeviceTestContext(Test, properties={'prop': 'a/b/c/d'}) as proxy:
        # Device not in fault
        assert proxy.state() == DevState.UNKNOWN
        # Run delete device
        proxy.delete()
        # Check info
        info = proxy.getinfo()
        assert "Cannot unsubscribe from attribute a/b/c/d" in info
        assert "Ooops" in info



def test_exception_on_monitor_lock(mocker):

    class Test(Facade):

        attr = proxy_attribute(
            dtype=float,
            property_name='prop')

    mocker.patch('facadedevice.utils.DeviceProxy')
    inner_proxy = utils.DeviceProxy.return_value
    inner_proxy.dev_name.return_value = 'a/b/c'
    subscribe_event = inner_proxy.subscribe_event
    monitor_mock = mocker.patch('facadedevice.utils.AutoTangoMonitor')
    monitor_mock.return_value.__enter__.side_effect = RuntimeError('Ooops')

    with DeviceTestContext(Test, properties={'prop': 'a/b/c/d'}) as proxy:
        # Device not in fault
        assert proxy.state() == DevState.UNKNOWN
        # Check mocks
        utils.DeviceProxy.assert_called_with('a/b/c')
        assert subscribe_event.called
        cb = subscribe_event.call_args[0][2]
        args = 'd', EventType.CHANGE_EVENT, cb, [], False
        subscribe_event.assert_called_with(*args)
        # Trigger events
        event = mocker.Mock(spec=EventData)
        event.attr_name = 'a/b/c/d'
        event.errors = False
        event.attr_value.value = 1.2
        event.attr_value.time.totime.return_value = 3.4
        event.attr_value.quality = AttrQuality.ATTR_ALARM
        cb(event)
        # Get info
        info = proxy.getinfo()
        assert 'Exception while running event callback' in info
        assert 'Ooops' in info
