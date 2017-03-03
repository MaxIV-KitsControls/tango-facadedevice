"""Provide the facade device class and metaclass"""

# Imports
import time
from collections import defaultdict
from contextlib import contextmanager

# Common imports
from facadedevice.common import Device
from facadedevice.common import safe_traceback, debug_it

# Object imports
from facadedevice.objects import logical_attribute
from facadedevice.objects import class_object, attribute_mapping, update_docs

# PyTango
from tango.server import device_property, command
from tango import DevFailed, DevState, EventData, EventType


# Proxy metaclass
class FacadeMeta(type(Device)):
    """Metaclass for Facade device."""

    def __new__(metacls, name, bases, dct):
        # Class attribute
        dct["_class_dict"] = class_dict = {
            "attributes": {},
            "commands":   {},
            "devices":    {}}
        # Inheritance
        for base in reversed(bases):
            try:
                base_class_dict = base._class_dict
            except AttributeError:
                continue
            # Copy _class_dict from the bases
            for type_key, object_dict in class_dict.items():
                for key, obj in base_class_dict[type_key].items():
                    # Allow to remove facade objects by setting them to None
                    if key not in dct:
                        object_dict[key] = obj
        # Proxy objects
        for key, value in dct.items():
            if isinstance(value, class_object):
                value.update_class(key, dct)
        # Update doc
        update_docs(dct)
        # Create device class
        return type(Device).__new__(metacls, name, bases, dct)


# Metaclassing manually for python compatibility
_Facade = FacadeMeta('_Facade', (Device,), {})


# Proxy device
class Facade(_Facade):
    """Provide base methods for a facade device."""

    # Reasons to ignore for errors in events
    reasons_to_ignore = ["API_PollThreadOutOfSync"]

    # Exception handling

    @property
    def connected(self):
        """Status of the connection with the proxies."""
        return not self._exception_origins

    @contextmanager
    def safe_context(self, exceptions=Exception, msg="", ignore=False):
        """Catch and handle errors.

        Args:
            exceptions (tuple list): exception to catch
            msg (string): add a custom message
            ignore (bool): don't stop the device
        """
        try:
            yield
        except exceptions as exc:
            if isinstance(exc, DevFailed) and exc.args:
                exc = exc.args[0]
            self.register_exception(exc, msg=msg, ignore=ignore)

    def clear_attributes(self, forced=()):
        """Clear attribute data, except for local and evented attributes.

        Attributes in forced argument will be cleared in any case.
        """
        for key, value in self._class_dict["attributes"].items():
            if key in forced or type(value) is logical_attribute:
                del self._data_dict[key]

    def register_exception(self, exc, msg="", origin=None, ignore=False):
        """Regsiter an exception and update the device properly."""
        # Stream traceback
        self.debug_stream(safe_traceback())
        # Exception as a string
        try:
            exc = exc.desc
        except AttributeError:
            exc = str(exc) if str(exc) else repr(exc)
        # Format status
        form = lambda x: x.capitalize() if x else x
        status = '\n'.join(filter(None, [form(msg), form(exc)]))
        # Stream error
        self.error_stream(status)
        # Save in history
        self._exception_history[status] += 1
        # Ignore exception
        if ignore:
            return status
        # Set state and status
        self._exception_origins.add(origin or exc)
        self.set_status(status, force=True)
        self.set_state(DevState.FAULT, force=True)
        # Clear data dict
        self.clear_attributes(forced=(origin,))
        return status

    def ignore_exception(self, exc, msg='', origin=None):
        return self.register_exception(
            exc, msg=msg, origin=origin, ignore=True)

    def recover_from(self, origin):
        """Recover from an error caused by the given origin."""
        self._exception_origins.discard(origin)

    def get_device_properties(self, cls=None):
        """Raise a ValueError if a property is missing."""
        Device.get_device_properties(self, cls)
        for key, value in self.device_property_list.items():
            if value[2] is None:
                raise ValueError('Missing property: ' + key)

    # Events handling

    def subscribe(self, device, attr, origin):
        callback = lambda event: self.on_event(origin, event)
        fullattr = '/'.join((device, attr))
        try:
            self.subscribe_event(
                fullattr, EventType.CHANGE_EVENT, callback)
        except DevFailed:
            try:
                self.subscribe_event(
                    fullattr, EventType.PERIODIC_EVENT, callback)
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
    def on_event(self, attr, event):
        """Handle attribute events."""
        # Ignore the event if not a data event
        if not isinstance(event, EventData):
            msg = "Received an unexpected event."
            self.register_exception(event, msg=msg)
            return
        # Format attribute name
        attr_name = '/'.join(event.attr_name.split('/')[-4:])
        # Ignore the event if it contains an error
        if event.errors:
            exc = event.errors[0]
            template = "Received an event from {0} that contains errors."
            msg = template.format(attr_name)
            ignore = getattr(exc, "reason", None) in self.reasons_to_ignore
            self.register_exception(exc, msg=msg, origin=attr, ignore=ignore)
            return
        # Info stream
        msg = "Received a valid event from {0} for attribute {1}."
        self.info_stream(msg.format(attr_name, attr))
        # Recover if needed
        self.recover_from(attr)
        # Save
        msg = "Error while saving event value for attribute {0}"
        with self.safe_context(msg=msg.format(attr), ignore=True):
            self._data_dict[attr] = event.attr_value
        # Update
        self.update()

    # Initialization

    def init_device(self):
        """Initialize the device."""
        # Init exception data structure
        self._exception_origins = set()
        self._exception_history = defaultdict(int)
        # Init events
        self.set_change_event('State', True, False)
        self.set_archive_event('State', True, True)
        self.set_change_event('Status', True, False)
        self.set_archive_event('Status', True, True)
        # Init mappings
        self._data_dict = attribute_mapping(self)
        # Initialize state
        self.set_state(DevState.INIT)
        self._init_stamp = time.time()
        # Handle properties
        with self.safe_context((TypeError, ValueError, KeyError)):
            super(Facade, self).init_device()  # get device properties
        # Invalid property case
        if self.get_state() != DevState.INIT:
            return
        # Connection
        with self.safe_context(DevFailed):
            self.init_connection()
        # Update
        self.update()

    @debug_it
    def delete_device(self):
        """Unsubscribe events and clear attributes values."""
        # Unsubscribe events
        super(Facade, self).delete_device()
        # Clear internal attributes
        self._data_dict.clear()

    def init_connection(self):
        """Initialize all connections."""
        # Get informations for proxies
        for device, value in sorted(self._class_dict["devices"].items()):
            value.init_connection(self)
        # Get informations for attributes
        for attr, value in sorted(self._class_dict["attributes"].items()):
            value.init_connection(self)
        # Get informations for commands
        for cmd, value in sorted(self._class_dict["commands"].items()):
            value.init_connection(self)

    # Update methods

    @debug_it
    def update(self):
        """Update logical attributes, state and status."""
        # Connection error
        if not self.connected:
            return
        # Safe update
        try:
            self.safe_update(self._data_dict)
        except Exception as exc:
            msg = "Error while running safe_update."
            self.ignore_exception(exc, msg=msg)
        # Update data
        for attr, value in sorted(self._class_dict["attributes"].items()):
            if not hasattr(value, 'update'):
                continue
            try:
                self._data_dict[attr] = value.update(self._data_dict)
            except Exception as exc:
                msg = "Error while updating attribute {0}.".format(attr)
                self.ignore_exception(exc, msg=msg)
                self._data_dict[attr] = None
        # Get state
        try:
            state = self.state_from_data(self._data_dict)
        except Exception as exc:
            msg = "Error while getting the device state."
            self.register_exception(exc, msg=msg)
            return
        # Set state
        if state is not None:
            self.set_state(state)
        # Get status
        try:
            status = self.status_from_data(self._data_dict)
        except Exception as exc:
            msg = "Error while getting the device status."
            status = self.ignore_exception(exc, msg=msg)
        # Set status
        if status is not None:
            self.set_status(status)

    def safe_update(self, data):
        """Safe update to overrride."""
        pass

    # Properties

    @property
    def data(self):
        """Data dictionary."""
        return self._data_dict

    # Method to override

    def state_from_data(self, data):
        """Method to override."""
        return None

    def status_from_data(self, data):
        """Method to override."""
        return None

    # State, status

    def set_state(self, state, force=False):
        """Set the state and push events if necessary."""
        if force or self.connected:
            super(Facade, self).set_state(state)
            self.push_change_event('State', state)
            self.push_archive_event('State', state)

    def set_status(self, status, force=False):
        """Set the status and push events if necessary."""
        if force or self.connected:
            super(Facade, self).set_status(status)
            self.push_change_event('Status', status)
            self.push_archive_event('Status', status)

    # Device properties

    HeavyLogging = device_property(
        dtype=bool,
        doc="Enable heavy logging.",
        default_value=False,
        )

    # Commands

    @command(
        dtype_out=str,
        doc_out="Information about polling and events."
        )
    def GetInfo(self):
        """Return information about polling and events."""
        lines = []
        # Connection
        if self.connected:
            lines.append("The device is currently connected.")
        else:
            lines.append("The device is currently stopped because of:")
            for origin in self._exception_origins:
                lines.append(" - {0!r}".format(origin))
        # Event subscription
        if any(self._evented_attrs.values()):
            lines.append("It subscribed to event channel "
                         "of the following attribute(s):")
            for local, remote in self.evented_attributes:
                lines.append("- {0}: {1}".format(local, remote))
        else:
            lines.append("It didn't subscribe to any event.")
        # Exception history
        lines.append("-" * 5)
        strtime = time.ctime(self._init_stamp)
        if self._exception_history:
            msg = "Error history since {0} (last initialization):"
            lines.append(msg.format(strtime))
            for key, value in self._exception_history.items():
                string = 'once' if value == 1 else '{0} times'.format(value)
                lines.append(' - Raised {0}:'.format(string))
                lines.extend(' ' * 4 + line for line in key.split('\n'))
        else:
            msg = "No errors in history since {0} (last initialization)."
            lines.append(msg.format(strtime))
        # Return result
        return '\n'.join(lines)
