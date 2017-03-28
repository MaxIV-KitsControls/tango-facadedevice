"""Provide the facade device class and metaclass"""

# Imports
import time

# Base imports
from facadedevice.graph import triplet, Graph, context, INVALID

# Common imports
from facadedevice.utils import EnhancedDevice, aggregate_qualities
from facadedevice.utils import to_dev_failed, get_default_attribute_value

# Object imports
from facadedevice.objects import class_object, local_attribute, NONE_STRING

# Tango imports
from tango.server import command
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

    # Helper

    def normalize_attribute_value(self, attr, value, stamp, quality):
        if value is None:
            quality = INVALID
        if quality == INVALID:
            dtype = attr.get_data_type()
            dformat = attr.get_data_format()
            value = get_default_attribute_value(dformat, dtype)
        return value, stamp, quality

    # Initialization

    def safe_init_device(self):
        """Initialize the device."""
        self._graph = Graph()
        # Get properties
        with context('getting', 'properties'):
            super(Facade, self).safe_init_device()
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

    # Event subscription

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

    # Event callback

    def on_node_event(self, node, event):
        """Handle node events."""
        # Ignore the event if not a data event
        if not isinstance(event, EventData):
            msg = "Received an unexpected event for {}"
            self.error_stream(msg.format(node))
            return
        # Format attribute name
        attr_name = '/'.join(event.attr_name.split('/')[-4:])
        # Ignore the event if it contains an error
        if event.errors:
            exc = DevFailed(*event.errors)
            reason = exc.args[0].reason
            msg = "Received an event from {} that contains errors"
            self.ignore_exception(exc, msg=msg.format(attr_name))
            if reason not in self.reasons_to_ignore:
                node.set_exception(exc)
            return
        # Info stream
        msg = "Received a valid event from {} for {}."
        self.info_stream(msg.format(attr_name, node))
        # Save
        value = triplet.from_attr_value(event.attr_value)
        node.set_result(value)

    # Client requests

    def read_from_node(self, node, attr=None):
        """Used when reading an attribute"""
        if node.result() is None:
            return
        value, stamp, quality = node.result()
        if attr:
            attr.set_value_date_quality(
                *self.normalize_attribute_value(
                    attr, value, stamp, quality))
        return value, stamp, quality

    def write_to_node(self, node, value):
        """Used when writing a local attribute"""
        result = triplet(value, time.time())
        node.set_result(result)

    def run_proxy_command(self, factory, prop, value):
        """Used when writing a proxy attribute"""
        return self.run_proxy_command_context(
            factory, prop,
            lambda subcommand, value: subcommand(value),
            value)

    def run_proxy_command_context(self, factory, prop, ctx, *values):
        """Used when running a proxy command"""
        name = getattr(self, prop).strip().lower()
        # Disabled command
        if name == NONE_STRING:
            raise ValueError('This proxy command is disabled')
        # Run subcommand in context
        subcommand = factory(getattr(self, prop))
        return ctx(subcommand, *values)

    # Controlled callbacks

    def run_callback(self, ctx, func, node):
        """Contexualize different node callbacks."""
        try:
            with context(ctx, node):
                func(node)
        except Exception as exc:
            self.ignore_exception(exc)

    def aggregate_for_node(self, node, func, *nodes):
        """Contextualize result and exception propagation."""
        with context("updating", node):
            # Forward first exception
            for node in nodes:
                if node.exception() is not None:
                    raise node.exception()
            # Shortcut for empty nodes
            results = [node.result() for node in nodes]
            if any(result is None for result in results):
                return
            # Exctract values
            values, stamps, qualities = zip(*results)
            # Invalid quality
            if any(quality == INVALID for quality in qualities):
                return triplet(None, max(stamps), INVALID)
            # Run function
            result = func(*values)
            # Return triplet
            if isinstance(result, triplet):
                return result
            # Create triplet
            if result is None:
                quality = INVALID
            else:
                quality = aggregate_qualities(qualities)
            return triplet(result, max(stamps), quality)

    # Dedicated callbacks

    def set_state_from_node(self, node):
        if node.exception() is not None:
            self.register_exception(node.exception())
        elif node.result() is None:
            self.set_state(DevState.UNKNOWN)
            self.set_status("The state is currently not available.")
        else:
            value, stamp, quality = node.result()
            try:
                if value is None or quality == INVALID:
                    state = DevState.FAULT
                    status = "The state cannot be computed."
                    status += " Some values are invalid."
                else:
                    state, status = value
            except TypeError:
                state = value
                status = "The device is in {} state.".format(value)
            self.set_state(state, stamp, quality)
            self.set_status(status, stamp, quality)

    def push_event_for_node(self, node):
        attr = getattr(self, node.name)
        # Exception
        if node.exception() is not None:
            exception = to_dev_failed(node.exception())
            self.push_change_event(node.name, exception)
            self.push_archive_event(node.name, exception)
        # Empty result
        elif node.result() is None:
            pass
        # Triplet result
        else:
            value, stamp, quality = \
                self.normalize_attribute_value(attr, *node.result())
            self.push_change_event(node.name, value, stamp, quality)
            self.push_archive_event(node.name, value, stamp, quality)

    # Clean up

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

    @Time.notify
    def on_time(self, node):
        pass

    @command(
        polling_period=1000,
        display_level=DispLevel.EXPERT)
    def UpdateTime(self):
        t = time.time()
        result = triplet(t, t)
        self.graph['Time'].set_result(result)
