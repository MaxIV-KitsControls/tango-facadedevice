"""Provide the facade device class and metaclass"""

# Imports
import time

# Base imports
from facadedevice.base import triplet, Graph, context

# Common imports
from facadedevice.common import EnhancedDevice, debug_it

# Object imports
from facadedevice.objects import class_object, local_attribute

# Tango imports
from tango.server import command
from tango import AttributeProxy
from tango import DevFailed, DevState, EventData, EventType, DispLevel


# Proxy metaclass

class FacadeMeta(type(EnhancedDevice)):
    """Metaclass for Facade device."""

    def __new__(metacls, name, bases, dct):
        # Class attribute
        dct["_class_dict"] = class_dict = {}
        # Inheritance
        for base in reversed(bases):
            try:
                base_class_dict = base._class_dict
            except AttributeError:
                continue
            # Copy _class_dict from the bases
            for key, obj in base_class_dict.items():
                # Allow to remove facade objects by setting them to None
                if key not in dct:
                    class_dict[key] = obj
        # Process class objects
        for key, value in list(dct.items()):
            if isinstance(value, class_object):
                class_dict[key] = value
                value.update_class(key, dct)
        # Create device class
        return type(EnhancedDevice).__new__(metacls, name, bases, dct)


# Metaclassing manually for python compatibility

_Facade = FacadeMeta('_Facade', (EnhancedDevice,), {})


# Facade device

class Facade(_Facade):
    """Provide base methods for a facade device."""

    # Reasons to ignore for errors in events
    reasons_to_ignore = ["API_PollThreadOutOfSync"]

    # Properties

    @property
    def graph(self):
        return self._graph

    # Helpers

    def write_attribute_from_property(self, prop, value):
        attr = getattr(self, prop)
        proxy = AttributeProxy(attr)
        proxy.write(value)

    # Events handling

    def subscribe_for_node(self, attr, node):
        try:
            self.subscribe_event(
                attr,
                EventType.CHANGE_EVENT,
                lambda event: self.on_node_event(node, event))
        except DevFailed:
            try:
                self.subscribe_event(
                    attr,
                    EventType.PERIODIC_EVENT,
                    lambda event: self.on_node_event(node, event))
            except DevFailed:
                msg = "Can't subscribe to event for attribute {}"
                self.info_stream(msg.format(attr))
                raise
            else:
                msg = "Subscribed to periodic event for attribute {}"
                self.info_stream(msg.format(attr))
                return EventType.PERIODIC_EVENT
        else:
            msg = "Subscribed to change event for attribute {}"
            self.info_stream(msg.format(attr))
            return EventType.CHANGE_EVENT

    @debug_it
    def on_node_event(self, node, event):
        """Handle attribute events."""
        # Ignore the event if not a data event
        if not isinstance(event, EventData):
            msg = "Received an unexpected event."
            self.ignore_exception(event, msg=msg)
            return
        # Format attribute name
        attr_name = '/'.join(event.attr_name.split('/')[-4:])
        # Ignore the event if it contains an error
        if event.errors:
            exc = event.errors[0]
            template = "Received an event from {0} that contains errors."
            msg = template.format(attr_name)
            if getattr(exc, "reason", None) in self.reasons_to_ignore:
                self.ignore_exception(exc, msg=msg, origin=node)
            else:
                node.set_exception(exc)
            return
        # Info stream
        msg = "Received a valid event from {0} for {1}."
        self.info_stream(msg.format(attr_name, node))
        # Save
        value = triplet.from_attr_value(event.attr_value)
        node.set_result(value)

    # Push events

    def set_state_from_node(self, node):
        if node.exception() is not None:
            self.register_exception(node.exception())
        elif node.result() is None:
            self.set_state(DevState.UNKNOWN)
            self.set_status("The state is currently not available.")
        else:
            value, stamp, quality = node.result()
            try:
                state, status = value
            except ValueError:
                state, status = value, "The state is {}".format(value)
            self.set_state(state, stamp, quality)
            self.set_status(status, stamp, quality)

    def push_event_for_node(self, node):
        attr = getattr(self, node.name)
        # Set events
        if not attr.is_archive_event():
            attr.set_archive_event(True, True)
        if not attr.is_change_event():
            attr.set_change_event(True, False)
        # Exception
        if node.exception() is not None:
            self.push_change_event(node.name, node.exception())
            self.push_archive_event(node.name, node.exception())
        elif node.result is None:
            pass
        else:
            value, stamp, quality = node.result()
            self.push_change_event(node.name, value, stamp, quality)
            self.push_archive_event(node.name, value, stamp, quality)

    # Read / write nodes

    def read_from_node(self, node, attr=None):
        if node.result() is None:
            return
        value, stamp, quality = node.result()
        if attr:
            attr.set_value_date_quality(value, stamp, quality)
        return value, stamp, quality

    def write_to_node(self, node, value):
        result = triplet(value, time.time())
        node.set_result(result)

    # Initialization and cleanup

    def init_device(self):
        """Initialize the device."""
        self._graph = Graph()
        # Configure
        for value in self._class_dict.values():
            with context('configuring', value):
                value.configure(self)
        # Build graph
        with context('building', self._graph):
            self._graph.build()
        # Connect
        for value in self._class_dict.values():
            with context('connecting', value):
                value.connect(self)

    def delete_device(self):
        # Reset graph
        try:
            self._graph.reset()
        except Exception as exc:
            msg = "Error while resetting the graph"
            self.ignore_exception(exc, msg)
        # Unsubscribe all
        super(Facade, self).delete_device()


# Timed Facade

class TimedFacade(Facade):

    def init_device(self):
        super(TimedFacade, self).init_device()
        self.UpdateTime()

    Time = local_attribute(dtype=float)

    @command(
        polling_period=1000,
        display_level=DispLevel.EXPERT)
    def UpdateTime(self):
        t = time.time()
        result = triplet(t, t)
        self.graph['Time'].set_result(result)
