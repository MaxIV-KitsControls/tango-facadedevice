"""Provide the facade device class and metaclass."""

# Imports
import time
import collections

# Graph imports
from facadedevice.graph import triplet, Graph, INVALID

# Exception imports
from facadedevice.exception import to_dev_failed, context

# Utils imports
from facadedevice.utils import EnhancedDevice, aggregate_qualities
from facadedevice.utils import get_default_attribute_value

# Object imports
from facadedevice.objects import class_object, local_attribute

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
    """Base class for facade devices.

    It supports the following objects:

    - `facadedevice.local_attribute`_
    - `facadedevice.logical_attribute`_
    - `facadedevice.proxy_attribute`_
    - `facadedevice.combined_attribute`_
    - `facadedevice.state_attribute`_
    - `facadedevice.proxy_command`_

    It also provides a few helpers:

    - `self.graph`: act as a `<key, node>` dictionnary
    - `self.get_combined_results`: return the subresults of a combined
      attribute

    The `init_device` method shouldn't be overridden. It performs specific
    exception handling. Instead, override `safe_init_device` if you have to
    add some extra logic. Don't forget to call the parent method since it
    performs a few useful steps:

    - load device properties
    - configure and build the graph
    - run the connection routine

    It also provides an expert command called `GetInfo` that displays useful
    information such as:

    - the connection status
    - the list of all event subscriptions
    - the exception history
    """

    # Reasons to ignore for errors in events
    reasons_to_ignore = ["API_PollThreadOutOfSync"]

    # Properties

    @property
    def graph(self):
        return self._graph

    # Helper

    def get_combined_results(self, name):
        """Return the subresults of a given combined attribute.

        It produces an ordered dictionnary of <attribute_name, triplet>.
        """
        subnodes = self.graph.subnodes(name)
        return collections.OrderedDict(
            (node.remote_attr, node.result()) for node in subnodes)

    def _get_default_value(self, attr):
        dtype = attr.get_data_type()
        dformat = attr.get_data_format()
        return get_default_attribute_value(dformat, dtype)

    def _emulate_subcommand(self, result, *args):
        if args or result is None:
            raise ValueError('This proxy command is disabled')
        return result

    # Initialization

    def safe_init_device(self):
        """Initialize the device."""
        # Init data structures
        self._graph = Graph()
        self._subcommand_dict = {}
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

    def _subscribe_for_node(self, attr, node):
        try:
            self.subscribe_event(
                attr,
                EventType.CHANGE_EVENT,
                lambda event: self._on_node_event(node, event))
        except DevFailed:
            try:
                self.subscribe_event(
                    attr,
                    EventType.PERIODIC_EVENT,
                    lambda event: self._on_node_event(node, event))
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

    def _on_node_event(self, node, event):
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

    def _read_from_node(self, node, attr=None):
        """Used when reading an attribute"""
        if node.result() is None:
            return
        value, stamp, quality = node.result()
        if attr:
            if value is None:
                value = self._get_default_value(attr)
            attr.set_value_date_quality(value, stamp, quality)
        return value, stamp, quality

    def _write_to_node(self, node, value):
        """Used when writing a local attribute"""
        node.set_result(triplet(value))

    def _run_proxy_command(self, key, value):
        """Used when writing a proxy attribute"""
        return self._run_proxy_command_context(
            key, lambda subcommand, value: subcommand(value), value)

    def _run_proxy_command_context(self, key, ctx, *values):
        """Used when running a proxy command"""
        # Run subcommand in context
        subcommand = self._subcommand_dict[key]
        return ctx(subcommand, *values)

    # Controlled callbacks

    def _run_callback(self, ctx, func, node):
        """Contexualize different node callbacks."""
        try:
            with context(ctx, node):
                func(node)
        except Exception as exc:
            self.ignore_exception(exc)

    def _standard_aggregation(self, node, func, *nodes):
        """Contextualize aggregation and propagate errors automatically."""
        # Forward first exception
        for subnode in nodes:
            if subnode.exception() is not None:
                with context("updating", node):
                    raise subnode.exception()
        # Shortcut for empty nodes
        results = [subnode.result() for subnode in nodes]
        if any(result is None for result in results):
            return
        # Exctract values
        values, stamps, qualities = zip(*results)
        # Invalid quality
        if any(quality == INVALID for quality in qualities):
            return triplet(None, max(stamps), INVALID)
        # Run function
        try:
            with context("updating", node):
                result = func(*values)
        except Exception as exc:
            self.ignore_exception(exc)
            raise exc
        # Return triplet
        if isinstance(result, triplet):
            return result
        # Create triplet
        quality = aggregate_qualities(qualities)
        return triplet(result, max(stamps), quality)

    def _custom_aggregation(self, node, func, *nodes):
        """Contextualize aggregation."""
        # Run function
        try:
            with context("updating", node):
                result = func(*nodes)
        except Exception as exc:
            self.ignore_exception(exc)
            raise exc
        # Return result
        if not isinstance(result, triplet):
            result = triplet(result)
        return result

    # Dedicated callbacks

    def _set_state_from_node(self, node):
        # Forward exception
        if node.exception() is not None:
            self.register_exception(node.exception())
            return
        # Empty node
        if node.result() is None:
            self.set_state(DevState.UNKNOWN)
            self.set_status("The state is currently not available.")
            return
        # Unpack triplet
        value, stamp, quality = node.result()
        # Invalid value
        if value is None:
            value = (
                DevState.FAULT,
                "The state cannot be computed. Some values are invalid.")
        # Unpack value
        try:
            state, status = value
        except (TypeError, ValueError):
            state = value
            status = "The device is in {} state.".format(value)
        # Set state and status
        try:
            with context('setting', 'state and status'):
                self.set_state(state, stamp, quality)
                self.set_status(status, stamp, quality)
        # Exception while setting the state
        except Exception as exc:
            self.register_exception(exc)

    def _push_event_for_node(self, node):
        attr = getattr(self, node.name)
        # Exception
        if node.exception() is not None:
            exception = to_dev_failed(node.exception())
            self.push_change_event(node.name, exception)
            self.push_archive_event(node.name, exception)
            # Log the pushing of exceptions
            msg = 'Pushing an exception for attribute {}'
            self.debug_exception(exception, msg.format(node.name))
        # Empty result
        elif node.result() is None:
            pass
        # Triplet result
        else:
            value, stamp, quality = node.result()
            if value is None:
                value = self._get_default_value(attr)
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
    """Similar to the `facadedevice.Facade` base class with time handling.

    In particular, it adds:

    - the `UpdateTime` polled command, used trigger updates periodically
    - the `Time` local attribute, a float updated at every tick
    - the `on_time` method, a callback that runs at every tick
    """

    def init_device(self):
        super(TimedFacade, self).init_device()
        self.UpdateTime()

    Time = local_attribute(dtype=float)

    @Time.notify
    def _on_time(self, node):
        self.on_time(node.result().value)

    def on_time(self, value):
        pass

    @command(
        polling_period=1000,
        display_level=DispLevel.EXPERT)
    def UpdateTime(self):
        t = time.time()
        result = triplet(t, t)
        self.graph['Time'].set_result(result)
