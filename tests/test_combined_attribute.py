"""Contain the tests for proxy device server."""

# Imports
import pytest
from unittest.mock import MagicMock, Mock, patch
from collections import namedtuple, OrderedDict

# Tango imports
from tango.test_context import DeviceTestContext
from tango import DevState, EventType, EventData, AttrQuality
from tango import AttrWriteType

# Facade imports
from facadedevice import Facade, combined_attribute, utils

# Local imports
from test_simple import event_mock


def test_combined_attribute():
    class Test(Facade):
        @combined_attribute(dtype=float, property_name="prop")
        def attr(self, *values):
            return sum(values)

        @attr.notify
        def on_attr(self, node):
            if node.exception() or node.result() is None:
                pass
            cb_mock(*node.result())

    cb_mock = MagicMock()

    change_events, archive_events = event_mock(Mock, Test)

    with patch("facadedevice.utils.DeviceProxy") as inner_proxy:
        inner_proxy = utils.DeviceProxy.return_value
        inner_proxy.dev_name.return_value = "a/b/c"
        subscribe_event = inner_proxy.subscribe_event

        props = {"prop": ["a/b/c/d", "e/f/g/h", "i/j/k/l"]}

        with DeviceTestContext(Test, properties=props) as proxy:
            # Device not in fault
            assert proxy.state() == DevState.UNKNOWN
            # Check mocks
            utils.DeviceProxy.assert_any_call("a/b/c")
            utils.DeviceProxy.assert_any_call("e/f/g")
            utils.DeviceProxy.assert_any_call("i/j/k")
            assert subscribe_event.called
            cbs = [x[0][2] for x in subscribe_event.call_args_list]
            for attr, cb in zip("dhl", cbs):
                args = attr, EventType.CHANGE_EVENT, cb, [], False
                subscribe_event.assert_any_call(*args)
            # No event pushed
            change_events["attr"].assert_not_called()
            archive_events["attr"].assert_not_called()
            # Trigger events
            event = MagicMock(spec=EventData)
            event.errors = False
            # First event
            event.attr_name = "a/b/c/d"
            event.attr_value.value = 1.1
            event.attr_value.time.totime.return_value = 0.1
            event.attr_value.quality = AttrQuality.ATTR_CHANGING
            cbs[0](event)
            # Second event
            event.attr_name = "e/f/g/h"
            event.attr_value.value = 2.2
            event.attr_value.time.totime.return_value = 0.2
            event.attr_value.quality = AttrQuality.ATTR_VALID
            cbs[1](event)
            # Third event
            event.attr_name = "i/j/k/l"
            event.attr_value.value = 3.3
            event.attr_value.time.totime.return_value = 0.3
            event.attr_value.quality = AttrQuality.ATTR_ALARM
            cbs[2](event)
            # Device not in fault
            assert proxy.state() == DevState.UNKNOWN
            # Check events
            expected = 6.6, 0.3, AttrQuality.ATTR_ALARM
            change_events["attr"].assert_called_once_with(*expected)
            archive_events["attr"].assert_called_once_with(*expected)
            cb_mock.assert_called_once_with(*expected)


def test_writable_combined_attribute():

    with pytest.raises(ValueError) as ctx:

        class Test(Facade):
            @combined_attribute(
                dtype=float,
                property_name="prop",
                access=AttrWriteType.READ_WRITE,
            )
            def attr(self, *values):
                return sum(values)

    message = str(ctx.value)
    assert "combined_attribute <attr> cannot be writable" in message


def test_combined_attribute_empty_prop():
    class Test(Facade):
        @combined_attribute(dtype=float, property_name="prop")
        def attr(self, *values):
            return sum(values)

    props = {"prop": [" ", " ", " "]}

    with DeviceTestContext(Test, properties=props) as proxy:
        assert proxy.state() == DevState.FAULT
        assert "Property 'prop' is empty" in proxy.status()


def test_disabled_combined_attribute():
    class Test(Facade):
        @combined_attribute(dtype=float, property_name="prop")
        def attr(self, *values):
            return sum(values)

    props = {"prop": ["None"]}

    with DeviceTestContext(Test, properties=props) as proxy:
        # The device not in fault
        print(proxy.status())
        assert proxy.state() == DevState.UNKNOWN
        # The attribute is not available
        assert proxy.attr is None


def test_combined_attribute_with_wildcard():
    class Test(Facade):
        @combined_attribute(dtype=float, property_name="prop")
        def attr(self, *values):
            return sum(values)

    named = namedtuple("named", "name")
    change_events, archive_events = event_mock(Mock, Test)
    with patch("facadedevice.utils.DeviceProxy") as inner_proxy:
        with patch("facadedevice.utils.Database") as inner_db:
            get_device_exported = inner_db.return_value.get_device_exported
            get_device_exported.return_value = ["a/b/c", "a/b/d", "a/b/e"]
            inner_proxy = utils.DeviceProxy.return_value
            inner_proxy.dev_name.return_value = "a/b/c"
            infos = [named(name) for name in "xyz"]
            inner_proxy.attribute_list_query.return_value = infos
            subscribe_event = inner_proxy.subscribe_event

            props = {"prop": ["a/b/*/z"]}

            with DeviceTestContext(Test, properties=props) as proxy:
                # Device not in fault
                assert proxy.state() == DevState.UNKNOWN
                # Check mocks
                utils.DeviceProxy.assert_any_call("a/b/c")
                utils.DeviceProxy.assert_any_call("a/b/d")
                utils.DeviceProxy.assert_any_call("a/b/e")
                assert subscribe_event.called
                cbs = [x[0][2] for x in subscribe_event.call_args_list]
                for attr, cb in zip("zzz", cbs):
                    args = attr, EventType.CHANGE_EVENT, cb, [], False
                    subscribe_event.assert_any_call(*args)
                # No event pushed
                change_events["attr"].assert_not_called()
                archive_events["attr"].assert_not_called()
                # Trigger events
                event = MagicMock(spec=EventData)
                event.errors = False
                # First event
                event.attr_name = "a/b/c/z"
                event.attr_value.value = 1.1
                event.attr_value.time.totime.return_value = 0.1
                event.attr_value.quality = AttrQuality.ATTR_CHANGING
                cbs[0](event)
                # Second event
                event.attr_name = "a/b/d/z"
                event.attr_value.value = 2.2
                event.attr_value.time.totime.return_value = 0.2
                event.attr_value.quality = AttrQuality.ATTR_VALID
                cbs[1](event)
                # Third event
                event.attr_name = "a/b/e/z"
                event.attr_value.value = 3.3
                event.attr_value.time.totime.return_value = 0.3
                event.attr_value.quality = AttrQuality.ATTR_ALARM
                cbs[2](event)
                # Device not in fault
                assert proxy.state() == DevState.UNKNOWN
                # Check events
                expected = 6.6, 0.3, AttrQuality.ATTR_ALARM
                change_events["attr"].assert_called_once_with(*expected)
                archive_events["attr"].assert_called_once_with(*expected)


def test_combined_attribute_with_empty_wildcard():
    class Test(Facade):
        @combined_attribute(dtype=float, property_name="prop")
        def attr(self, *values):
            return sum(values)

    with patch("facadedevice.utils.DeviceProxy"):
        with patch("facadedevice.utils.Database") as inner_db:
            get_device_exported = inner_db.return_value.get_device_exported
            get_device_exported.return_value = ["a/b/c", "a/b/d", "a/b/e"]

            props = {"prop": ["i/j/*/z"]}

            with DeviceTestContext(Test, properties=props) as proxy:
                # Device not in fault
                assert proxy.state() == DevState.FAULT
                expected = "No attributes matching i/j/*/z wildcard"
                assert expected in proxy.status()


def test_combined_attribute_non_exposed():
    class Test(Facade):
        @combined_attribute(create_attribute=False, property_name="prop")
        def attr(self, *values):
            return sum(values)

        @attr.notify
        def on_attr(self, node):
            if node.exception() or node.result() is None:
                pass
            cb_mock(*node.result())

    cb_mock = MagicMock()

    with patch("facadedevice.utils.DeviceProxy") as inner_proxy:
        inner_proxy = utils.DeviceProxy.return_value
        inner_proxy.dev_name.return_value = "a/b/c"
        subscribe_event = inner_proxy.subscribe_event

        props = {"prop": ["a/b/c/d", "e/f/g/h", "i/j/k/l"]}

        with DeviceTestContext(Test, properties=props) as proxy:
            # Device not in fault
            assert proxy.state() == DevState.UNKNOWN
            # Check mocks
            utils.DeviceProxy.assert_any_call("a/b/c")
            utils.DeviceProxy.assert_any_call("e/f/g")
            utils.DeviceProxy.assert_any_call("i/j/k")
            assert subscribe_event.called
            cbs = [x[0][2] for x in subscribe_event.call_args_list]
            for attr, cb in zip("dhl", cbs):
                args = attr, EventType.CHANGE_EVENT, cb, [], False
                subscribe_event.assert_any_call(*args)
            # Trigger events
            event = MagicMock(spec=EventData)
            event.errors = False
            # First event
            event.attr_name = "a/b/c/d"
            event.attr_value.value = 1.1
            event.attr_value.time.totime.return_value = 0.1
            event.attr_value.quality = AttrQuality.ATTR_CHANGING
            cbs[0](event)
            # Second event
            event.attr_name = "e/f/g/h"
            event.attr_value.value = 2.2
            event.attr_value.time.totime.return_value = 0.2
            event.attr_value.quality = AttrQuality.ATTR_VALID
            cbs[1](event)
            # Third event
            event.attr_name = "i/j/k/l"
            event.attr_value.value = 3.3
            event.attr_value.time.totime.return_value = 0.3
            event.attr_value.quality = AttrQuality.ATTR_ALARM
            cbs[2](event)
            # Device not in fault
            assert proxy.state() == DevState.UNKNOWN
            # Check events
            expected = 6.6, 0.3, AttrQuality.ATTR_ALARM
            cb_mock.assert_called_once_with(*expected)


def test_get_combined_results():
    class Test(Facade):
        @combined_attribute(create_attribute=False, property_name="prop")
        def attr(self, *values):
            return self.get_combined_results("attr")

        @attr.notify
        def on_attr(self, node):
            if node.exception() or node.result() is None:
                pass
            cb_mock(*node.result())

    cb_mock = MagicMock()

    with patch("facadedevice.utils.DeviceProxy") as inner_proxy:
        inner_proxy = utils.DeviceProxy.return_value
        inner_proxy.dev_name.return_value = "a/b/c"
        subscribe_event = inner_proxy.subscribe_event

        props = {"prop": ["a/b/c/d", "e/f/g/h", "i/j/k/l"]}

        with DeviceTestContext(Test, properties=props, debug=3) as proxy:
            # Device not in fault
            assert proxy.state() == DevState.UNKNOWN
            # Check mocks
            utils.DeviceProxy.assert_any_call("a/b/c")
            utils.DeviceProxy.assert_any_call("e/f/g")
            utils.DeviceProxy.assert_any_call("i/j/k")
            assert subscribe_event.called
            cbs = [x[0][2] for x in subscribe_event.call_args_list]
            for attr, cb in zip("dhl", cbs):
                args = attr, EventType.CHANGE_EVENT, cb, [], False
                subscribe_event.assert_any_call(*args)
            # Trigger events
            event = MagicMock(spec=EventData)
            event.errors = False
            # First event
            event.attr_name = "a/b/c/d"
            event.attr_value.value = 1.1
            event.attr_value.time.totime.return_value = 0.1
            event.attr_value.quality = AttrQuality.ATTR_CHANGING
            cbs[0](event)
            # Second event
            event.attr_name = "e/f/g/h"
            event.attr_value.value = 2.2
            event.attr_value.time.totime.return_value = 0.2
            event.attr_value.quality = AttrQuality.ATTR_VALID
            cbs[1](event)
            # Third event
            event.attr_name = "i/j/k/l"
            event.attr_value.value = 3.3
            event.attr_value.time.totime.return_value = 0.3
            event.attr_value.quality = AttrQuality.ATTR_ALARM
            cbs[2](event)
            # Device not in fault
            assert proxy.state() == DevState.UNKNOWN
            # Check events
            odict = OrderedDict(
                [
                    ("a/b/c/d", (1.1, 0.1, AttrQuality.ATTR_CHANGING)),
                    ("e/f/g/h", (2.2, 0.2, AttrQuality.ATTR_VALID)),
                    ("i/j/k/l", (3.3, 0.3, AttrQuality.ATTR_ALARM)),
                ]
            )
            expected = odict, 0.3, AttrQuality.ATTR_ALARM
            cb_mock.assert_called_once_with(*expected)
