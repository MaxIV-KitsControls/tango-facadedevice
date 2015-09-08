"""Provide the facade device class and metaclass"""

# Imports
import traceback
from threading import Lock
from functools import partial
from collections import defaultdict
from contextlib import contextmanager
from facadedevice.common import cache_during, debug_it
from facadedevice.common import DeviceMeta, read_attributes
from facadedevice.objects import logical_attribute, update_docs
from facadedevice.objects import class_object, attribute_mapping

# PyTango
from PyTango.server import Device, device_property, command
from PyTango import DeviceProxy, DevFailed, DevState, EventType, EventData


# Proxy device
class Facade(Device):
    """Provide base methods for a facade device."""
    __metaclass__ = DeviceMeta

    # Disable push_events by default
    push_events = False
    update_period = 0

    # Helpers

    @property
    def ensure_events(self):
        """Events have to be used for all attributes."""
        return self.push_events and self.update_period <= 0

    @property
    def limit_period(self):
        """Limit the refresh rate for the remote update."""
        return 0 if self.push_events else self.update_period

    @property
    def poll_update_command(self):
        """Poll the update command to refresh values."""
        return self.push_events and not self.ensure_events

    @property
    def connected(self):
        """Status of the connection with the proxies."""
        return not self._exception_origins

    @property
    def require_attribute_polling(self):
        """True if at least one attributes require polling."""
        return any(self.polled_attributes)

    @property
    def polled_attributes(self):
        """List polled attributes as (local name, proxy name)."""
        for device, attr_dict in self._read_dict.items():
            proxy = self._proxy_dict[device]
            if not proxy:
                continue
            for attr, attr_proxy in attr_dict.items():
                if attr_proxy not in self._evented_attrs[proxy]:
                    attr_name = proxy.dev_name() + '/' + attr_proxy
                    yield attr, attr_name

    @property
    def evented_attributes(self):
        """List evented attributes as (local name, proxy name)."""
        for proxy, dct in self._evented_attrs.items():
            for attr_proxy, (attr, eid) in dct.items():
                attr_name = proxy.dev_name() + '/' + attr_proxy
                yield attr, attr_name

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
            if isinstance(exc, DevFailed):
                exc = exc.args[0]
            self.register_exception(exc, msg, ignore)

    # Exception handling

    def clear_attributes(self):
        """Clear attribute data, except for local attributes."""
        for key, value in self._class_dict["attributes"].items():
            if isinstance(value, logical_attribute):
                del self._data_dict[key]

    def register_exception(self, exc, msg="", origin=None, ignore=False):
        """Regsiter an exception and update the device properly."""
        # Stream traceback
        self.debug_stream(traceback.format_exc().replace("%", "%%"))
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
        # Lock state and status by registering an exception
        self._exception_origins.add(origin or exc)
        # Safely set state and status
        self.set_status(status, force=True)
        self.set_state(DevState.FAULT, force=True)
        # Clear data dict
        self.clear_attributes()
        return status

    def recover_from(self, origin):
        """Recover from an error caused by the given origin."""
        self._exception_origins.discard(origin)

    def get_device_properties(self, cls=None):
        """Raise a ValueError if a property is missing."""
        Device.get_device_properties(self, cls)
        for key, value in self.device_property_list.items():
            if value[2] is None:
                raise ValueError('missing property: ' + key)

    # Events handling

    @debug_it
    def on_change_event(self, attr, event):
        "Handle attribute change events"
        # Ignore the event if not a data event
        if not isinstance(event, EventData):
            msg = "Received an unexpected event."
            self.register_exception(event, msg)
            return
        # Format attribute name
        attr_name = '/'.join(event.attr_name.split('/')[-4:])
        # Ignore the event if it contains an error
        if event.errors:
            exc = event.errors[0]
            template = "Received an event from {0} that contains errors."
            msg = template.format(attr_name)
            self.register_exception(exc, msg, origin=attr)
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
        self.local_update()

    def configure_events(self):
        """Configure events and update period from property."""
        self.push_events = self.PushEvents
        self.update_period = self.UpdatePeriod
        # Enable push events for state and status
        if self.push_events:
            self.set_change_event('State', True, True)
            self.set_change_event('Status', True, True)
        # Poll update command
        if self.poll_update_command:
            ms = int(1000 * self.update_period)
            self.poll_command("Update", ms)
            return
        # Don't poll update command
        try:
            self.stop_poll_command("Update")
        except DevFailed as exc:
            self.info_stream('Update command is already stopped')
            self.debug_stream(str(exc))

    # Initialization

    def init_device(self):
        """Initialize the device."""
        # Init exception data structure
        self._exception_lock = Lock()
        self._exception_origins = set()
        self._exception_history = defaultdict(int)
        # Initialize state
        self.set_state(DevState.INIT)
        # Init mappings
        self._tmp_dict = {}
        self._proxy_dict = {}
        self._device_dict = {}
        self._method_dict = {}
        self._command_dict = {}
        self._evented_attrs = {}
        self._attribute_dict = {}
        self._read_dict = defaultdict(dict)
        self._data_dict = attribute_mapping(self)
        # Handle properties
        with self.safe_context((TypeError, ValueError, KeyError)):
            self.get_device_properties()
            self.configure_events()
        # Invalid property case
        if self.get_state() != DevState.INIT:
            return
        # Data structure
        self.init_data_structure()
        # Connection
        self.init_connection()

    def delete_device(self):
        """Unsubscribe events and clear attributes values."""
        # Unsubscribe events
        for proxy, attrs in self._evented_attrs.items():
            for attr, (key, eid) in attrs.items():
                try:
                    proxy.unsubscribe_event(eid)
                except Exception as exc:
                    self.debug_stream(str(exc))
                    msg = "Cannot unsubscribe from change event for attribute"
                else:
                    msg = "Unsubscribed from change event for attribute"
                finally:
                    msg += " {0}/{1}".format(proxy.dev_name(), attr)
                    self.info_stream(msg)
        # Clear cache from cache decorator
        self.remote_update.pop_cache(self)
        # Clear internal attributes
        self._data_dict.clear()
        # Disable events
        try:
            del self.push_events
        except AttributeError:
            pass

    def init_data_structure(self):
        """Initialize the internal data structures."""
        # Get informations for proxies
        for device, value in self._class_dict["devices"].items():
            proxy_name = getattr(self, value.device)
            self._device_dict[device] = proxy_name
        # Get informations for attributes
        for attr, value in sorted(self._class_dict["attributes"].items()):
            if value.attr and value.device:
                proxy_attr = getattr(self, value.attr)
                if proxy_attr.strip().lower() == "none":
                    continue
                proxy_name = getattr(self, value.device)
                self._attribute_dict[attr] = proxy_attr
                self._read_dict[proxy_name][attr] = proxy_attr
            if value.method:
                self._method_dict[attr] = value.method.__get__(self)
        # Get informations for commands
        for cmd, value in self._class_dict["commands"].items():
            attr = getattr(self, value.attr)
            self._command_dict[cmd] = (attr, value.value,
                                       value.reset_value, value.reset_delay)

    def init_connection(self):
        """Initialize all connections."""
        self.create_proxies()
        self.remote_update()
        self.local_update()
        self.setup_listeners()

    def create_proxies(self):
        """Create the device proxies."""
        # Connection error
        if self._exception_origins:
            return
        # Create proxies
        msg = "Cannot connect to proxy."
        with self.safe_context(DevFailed, msg):
            # Connect to proxies
            for device in self._device_dict.values():
                if device not in self._proxy_dict:
                    if device.strip().lower() == "none":
                        proxy = None
                    else:
                        proxy = DeviceProxy(device)
                    self._proxy_dict[device] = proxy
                    self._evented_attrs[proxy] = {}

    # Setup listeners

    def setup_listeners(self):
        """Try to setup listeners for all attributes."""
        # Connection error
        if self._exception_origins:
            return
        # Setup listeners
        msg = "Cannot subscribe to change event."
        with self.safe_context(DevFailed, msg):
            for device, attr_dict in self._read_dict.items():
                proxy = self._proxy_dict[device]
                # Diasbled proxy
                if not proxy:
                    continue
                # Setup listener
                self.setup_listener(proxy, attr_dict)

    def setup_listener(self, proxy, attr_dict):
        "Try to setup event listeners for all given attributes on a proxy"
        for attr, attr_proxy in attr_dict.items():
            try:
                eid = proxy.subscribe_event(
                    attr_proxy,
                    EventType.CHANGE_EVENT,
                    partial(self.on_change_event, attr))
            except DevFailed:
                msg = "Can't subscribe to change event for attribute {0}/{1}"
                self.info_stream(msg.format(proxy.dev_name(), attr_proxy))
                if self.ensure_events:
                    raise
            else:
                self._evented_attrs[proxy][attr_proxy] = attr, eid
                msg = "Subscribed to change event for attribute {0}/{1}"
                self.info_stream(msg.format(proxy.dev_name(), attr_proxy))

    # Update methods

    @cache_during("limit_period", "debug_stream")
    def remote_update(self):
        """Update the attributes by reading from the proxies."""
        # Connection error
        if not self.connected:
            return
        # Try to access the proxy
        msg = "Cannot read from proxy."
        errors = DevFailed, TypeError, ValueError
        with self.safe_context(errors, msg):
            # Read data
            for device, attr_dict in self._read_dict.items():
                proxy = self._proxy_dict[device]
                # Disabled proxy
                if not proxy:
                    continue
                # Filter attribute dict
                polled = dict((attr, attr_proxy)
                              for attr, attr_proxy in attr_dict.items()
                              if attr_proxy not in self._evented_attrs[proxy])
                # Read attributes
                values = polled and read_attributes(proxy, polled.values())
                # Store data
                for attr, value in zip(polled, values):
                    self._data_dict[attr] = value

    @debug_it
    def local_update(self):
        """Update logical attributes, state and status."""
        # Connection error
        if not self.connected:
            return
        # Safe update
        try:
            self.safe_update(self._data_dict)
        except Exception as exc:
            msg = "Error while running safe_update."
            self.register_exception(exc, msg, ignore=True)
        # Update data
        for key, method in self._method_dict.items():
            try:
                self._data_dict[key] = method(self._data_dict)
            except Exception as exc:
                msg = "Error while updating attribute {0}.".format(key)
                self.register_exception(exc, msg, ignore=True)
                self._data_dict[key] = None
        # Get state
        try:
            state = self.state_from_data(self._data_dict)
        except Exception as exc:
            msg = "Error while getting the device state."
            self.register_exception(exc, msg)
            return
        # Set state
        if state is not None:
            self.set_state(state)
        # Get status
        try:
            status = self.status_from_data(self._data_dict)
        except Exception as exc:
            msg = "Error while getting the device status."
            status = self.register_exception(exc, msg, ignore=True)
        # Set status
        if status is not None:
            self.set_status(status)

    def safe_update(self, data):
        """Safe update to overrride."""
        pass

    def update_all(self):
        """Update all."""
        # Connection error
        if not self.connected:
            return
        if self.require_attribute_polling:
            self.remote_update()
        self.local_update()

    # Properties

    @property
    def data(self):
        """Data dictionary."""
        return self._data_dict

    @property
    def devices(self):
        """The proxy dictionary."""
        return dict((key, self._proxy_dict[value])
                    for key, value in self._device_dict.items())

    @property
    def attributes(self):
        """The attribute dictionary."""
        return self._attribute_dict

    @property
    def commands(self):
        """The command dictionary."""
        return self._command_dict

    @property
    def methods(self):
        """The command dictionary."""
        return self._method_dict

    # Method to override

    def state_from_data(self, data):
        """Method to override."""
        return None

    def status_from_data(self, data):
        """Method to override."""
        return None

    # Update device

    def read_attr_hardware(self, attr):
        """Update attributes."""
        if not self.push_events:
            self.update_all()

    def dev_state(self):
        """Update attributes and return the state."""
        if not self.push_events:
            self.update_all()
        return Device.dev_state(self)

    # State, status and lock

    def set_state(self, state, force=False):
        """Set the state and push events if necessary."""
        with self._exception_lock:
            if force or self.connected:
                Device.set_state(self, state)
        if self.push_events:
            self.push_change_event('State')

    def set_status(self, status, force=False):
        """Set the status and push events if necessary."""
        with self._exception_lock:
            if force or self.connected:
                Device.set_status(self, status)
        if self.push_events:
            self.push_change_event('Status')

    # Device properties

    UpdatePeriod = device_property(
        dtype=float,
        doc="Set the refresh rate for polled attributes.",
        default_value=0.0,
        )

    PushEvents = device_property(
        dtype=bool,
        doc="Enable change events for all attributes.",
        default_value=False,
        )

    # Commands

    @command
    def Update(self):
        """Force the update of polled attributes."""
        self.update_all()

    @command(
        dtype_out=str,
        doc_out="Information about polling and events."
        )
    def GetInfo(self):
        """Return information about polling and events."""
        lines = []
        # Event sending
        if self.push_events:
            lines.append("This device pushes change events.")
        else:
            lines.append("This device does not push change events.")
        # Event subscription
        if self.ensure_events:
            lines.append("It ensures the event subscribtion "
                         "for all forwarded attributes.")
        elif any(self._evented_attrs.values()):
            lines.append("It subscribed to change event "
                         "for the following attribute(s):")
            for local, remote in self.evented_attributes:
                lines.append("- {0}: {1}".format(local, remote))
        else:
            lines.append("It didn't subscribe to any event.")
        # Attribute polling
        if self.require_attribute_polling:
            lines.append("It is polling the following attribute(s):")
            for local, remote in self.polled_attributes:
                lines.append("- {0}: {1}".format(local, remote))
        else:
            lines.append("It doesn't poll any attribute from another device.")
        # Polling and caching
        if self.limit_period > 0:
            line = ("It limits the calls to other devices "
                    "by caching the read values for {0:.3f} seconds.")
            lines.append(line.format(self.limit_period))
        elif self.poll_update_command:
            line = ("It refreshes its contents by polling "
                    "the update command every {0:.3f} seconds.")
            lines.append(line.format(self.update_period))
        elif self.push_events:
            lines.append("It doesn't rely on any polling.")
        else:
            lines.append("It doesn't use any caching "
                         "to limit the calls the other devices.")
        # Exception history
        lines.append("-" * 5)
        if self._exception_history:
            lines.append("Error history:")
            for key, value in self._exception_history.items():
                string = 'once' if value == 1 else '{0} times'.format(value)
                lines.append(' - Raised {0}:'.format(string))
                lines.extend(' ' * 4 + line for line in key.split('\n'))
        else:
            lines.append("No errors in the history.")
        # Return result
        return '\n'.join(lines)


# Proxy metaclass
def FacadeMeta(name, bases, dct):
    """Metaclass for Facade device.

    Return a FacadeMeta instance.
    """
    # Class attribute
    dct["_class_dict"] = {"attributes": {},
                          "commands":   {},
                          "devices":    {}}
    # Inheritance
    for base in reversed(bases):
        try:
            for key, value in dct["_class_dict"].items():
                value.update(base._class_dict.get(key, {}))
        except AttributeError:
            continue
    # Proxy objects
    for key, value in dct.items():
        if isinstance(value, class_object):
            value.update_class(key, dct)
    # Update doc
    update_docs(dct)
    # Create device class
    return DeviceMeta(name, bases, dct)
