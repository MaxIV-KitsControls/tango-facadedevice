"""Provide the facade device class and metaclass"""

# Imports
import time

# Base imports
from facadedevice.base import triplet, Graph

# Common imports
from facadedevice.common import EnhancedDevice, debug_it

# Object imports
from facadedevice.objects import class_object, update_docs, local_attribute

# Tango imports
from tango.server import command
from tango import DevFailed, EventData, EventType, DispLevel


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
        # Proxy objects
        for key, value in dct.items():
            if isinstance(value, class_object):
                value.update_class(key, dct)
        # Update doc
        update_docs(dct)
        # Create device class
        return type(EnhancedDevice).__new__(metacls, name, bases, dct)


# Metaclassing manually for python compatibility

_Facade = FacadeMeta('_Facade', (EnhancedDevice,), {})


# Facade device

class Facade(_Facade):
    """Provide base methods for a facade device."""

    # Reasons to ignore for errors in events
    reasons_to_ignore = ["API_PollThreadOutOfSync"]

    # Helpers

    @property
    def graph(self):
        return self._graph

    # Events handling

    def subscribe(self, device, attr, node):
        fullattr = '/'.join((device, attr))
        try:
            self.subscribe_event(
                fullattr,
                EventType.CHANGE_EVENT,
                lambda event: self.on_event(node, event))
        except DevFailed:
            try:
                self.subscribe_event(
                    fullattr,
                    EventType.PERIODIC_EVENT,
                    lambda event: self.on_event(node, event))
            except DevFailed:
                msg = "Can't subscribe to event for attribute {}"
                self.info_stream(msg.format(fullattr))
                raise
            else:
                msg = "Subscribed to periodic event for attribute {}"
                self.info_stream(msg.format(fullattr))
                return EventType.PERIODIC_EVENT
        else:
            msg = "Subscribed to change event for attribute {}"
            self.info_stream(msg.format(fullattr))
            return EventType.CHANGE_EVENT

    @debug_it
    def on_event(self, node, event):
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

    # Initialization and cleanup

    def init_device(self):
        """Initialize the device."""
        self._graph = Graph()
        # Configure
        try:
            for value in self._class_dict.values():
                value.configure(self)
        except Exception as exc:
            msg = "Error while configuring the device"
            self.register_exception(exc, msg)
            return
        # Build graph
        try:
            self._graph.build()
        except Exception as exc:
            msg = "Error while building the graph"
            self.register_exception(exc, msg)
            return
        # Connect
        try:
            for value in self._class_dict.values():
                value.connect(self)
        except Exception as exc:
            self._graph.reset()
            msg = "Error while connecting the device"
            self.register_exception(exc, msg)
            return
        # Success !
        return True

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

    Time = local_attribute(dtype=float)

    @command(
        polling_period=1000,
        display_level=DispLevel.EXPERT)
    def UpdateTime(self):
        self.graph['Time'] = time.time()
