"""Provide the facade device class and metaclass"""

# Imports
import time
from collections import defaultdict
from contextlib import contextmanager

# Common imports
from facadedevice.common import cache_during, debug_it, create_device_proxy
from facadedevice.common import Device, DeviceMeta, read_attributes
from facadedevice.common import tangocmd_exist, is_writable_attribute
from facadedevice.common import safe_traceback, NONE_STRING

# Object imports
from facadedevice.objects import logical_attribute, block_attribute
from facadedevice.objects import class_object, attribute_mapping, update_docs

# PyTango
from PyTango.server import device_property, command
from PyTango import DevFailed, DevState, EventType, EventData


# Proxy device
class Facade(Device):
    """Provide base methods for a facade device."""
    __metaclass__ = DeviceMeta

    # Disable push_events by default
    push_events = False
    update_period = 0

    # Reasons to ignore for errors in events
    reasons_to_ignore = ["API_PollThreadOutOfSync"]

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
        if self.ensure_events:
            return
        for device, attr_dict in self._read_dict.items():
            proxy = self._proxy_dict.get(device)
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
            if isinstance(exc, DevFailed) and exc.args:
                exc = exc.args[0]
            self.register_exception(exc, msg=msg, ignore=ignore)

    # Exception handling

    def clear_attributes(self, forced=()):
        """Clear attribute data, except for local and evented attributes.

        Attributes in forced argument will be cleared in any case."""
        evented = [attr for attr, attr_name in self.evented_attributes]
        for key, value in self._class_dict["attributes"].items():
            non_local = isinstance(value, logical_attribute)
            if key in forced or non_local and key not in evented:
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
                raise ValueError('missing property: ' + key)

    # Events handling

    @debug_it
    def on_change_event(self, attr, event):
        "Handle attribute change events"
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
        self._exception_origins = set()
        self._exception_history = defaultdict(int)
        # Initialize state
        self.set_state(DevState.INIT)
        self._init_stamp = time.time()
        # Init mappings
        self._tmp_dict = {}
        self._proxy_dict = {}
        self._device_dict = {}
        self._method_dict = {}
        self._command_dict = {}
        self._evented_attrs = {}
        self._attribute_dict = {}
        self._read_dict = defaultdict(dict)
        self._block_dict = defaultdict(dict)
        self._data_dict = attribute_mapping(self)
        # Handle properties
        with self.safe_context((TypeError, ValueError, KeyError)):
            super(Facade, self).init_device()  # get device properties
            self.configure_events()
        # Invalid property case
        if self.get_state() != DevState.INIT:
            return
        # Data structure
        self.init_data_structure()
        # Connection
        self.init_connection()
        # Check proxy_commands attributes exist
        self.check_proxy_commands()

    def delete_device(self):
        """Unsubscribe events and clear attributes values."""
        # Unsubscribe events
        super(Facade, self).delete_device()
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
            # Get attribute proxy name
            if value.prop:
                attr_name = getattr(self, value.prop)
            else:
                attr_name = value.attr
            # Set up read dictionary
            if attr_name and value.device:
                proxy_name = self._device_dict[attr]
                if attr_name.strip().lower() == NONE_STRING:
                    pass
                elif isinstance(value, block_attribute):
                    self._block_dict[proxy_name][attr] = attr_name
                    self._attribute_dict[attr] = attr_name + '*'
                else:
                    self._attribute_dict[attr] = attr_name
                    self._read_dict[proxy_name][attr] = attr_name
            # Set up method dictionary
            if value.method:
                self._method_dict[attr] = value.method.__get__(self)
        # Get informations for commands
        for cmd, value in self._class_dict["commands"].items():
            # Get proxy name
            if value.prop:
                proxy_name = getattr(self, value.prop)
            else:
                proxy_name = value.attr or value.cmd
            # Set up commad dict
            self._command_dict[cmd] = (proxy_name, value.is_attr, value.value,
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
                    if device.strip().lower() == NONE_STRING:
                        proxy = None
                    else:
                        proxy = create_device_proxy(device)
                        self.init_block_attributes(device, proxy)
                    self._proxy_dict[device] = proxy
                    self._evented_attrs[proxy] = {}

    def init_block_attributes(self, device, proxy):
        """Handle block attributes."""
        if device not in self._block_dict:
            return
        remote_list = proxy.get_attribute_list()
        for local, prefix in self._block_dict[device].items():
            local_list = []
            for remote in remote_list:
                if remote.lower().startswith(prefix.lower()):
                    name = local + '.' + remote[len(prefix):]
                    self._read_dict[device][name] = remote
                    self._data_dict.key_list.append(name)
                    local_list.append(name)
            self._block_dict[device][local] = local_list

    def check_proxy_commands(self):
        """ Check if proxy commands attributes exist and are writable. """
        errors = ""
        warnings = ""
        for cmd_name, cmd_args in self._command_dict.iteritems():
            # unpack
            attr_name, is_attr, cmd_value, _, _ = cmd_args
            if attr_name.strip().lower() == NONE_STRING:
                warn = "- Command '{0}' disabled: attribute is set to '{1}'\n"
                warnings += warn.format(cmd_name, attr_name)
                continue
            proxy_name = self._device_dict[cmd_name]
            device_proxy = self._proxy_dict[proxy_name]
            if is_attr:
                # proxy command writes in tango attribute
                writable, desc = is_writable_attribute(attr_name, device_proxy)
                if not writable:
                    # attribute is not writable
                    err_msg = "- Command '{0}' failure: {1}\n"
                    errors += err_msg.format(cmd_name, desc)
            else:
                # proxy command is a forwarded command
                cmd_exists, desc = tangocmd_exist(attr_name, device_proxy)
                if not cmd_exists:
                    err_msg = "- Command '{0}' failure: {1}\n"
                    errors += err_msg.format(cmd_name, desc)
        if errors:
            self.register_exception(errors, msg="Proxy command errors:")
        if warnings:
            self.ignore_exception(warnings, msg="Proxy command warnings:")

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
            cb = lambda event, attr=attr: self.on_change_event(attr, event)
            try:
                eid = self.subscribe_event(
                    attr_proxy, EventType.CHANGE_EVENT, cb, proxy=proxy)
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
            self.ignore_exception(exc, msg=msg)
        # Update data
        for key, method in self._method_dict.items():
            try:
                self._data_dict[key] = method(self._data_dict)
            except Exception as exc:
                msg = "Error while updating attribute {0}.".format(key)
                self.ignore_exception(exc, msg=msg)
                self._data_dict[key] = None
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

    def update_all(self):
        """Update all."""
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

    # State, status

    def set_state(self, state, force=False):
        """Set the state and push events if necessary."""
        if force or self.connected:
            Device.set_state(self, state)
        if self.push_events:
            self.push_change_event('State')

    def set_status(self, status, force=False):
        """Set the status and push events if necessary."""
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

    HeavyLogging = device_property(
        dtype=bool,
        doc="Enable heavy logging.",
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
        # Connection
        if self.connected:
            lines.append("The device is currently connected.")
        else:
            lines.append("The device is currently stopped because of:")
            for origin in self._exception_origins:
                lines.append(" - {0!r}".format(origin))
        # Event sending
        if self.push_events:
            lines.append("It pushes change events.")
        else:
            lines.append("It does not push change events.")
        # Event subscription
        if any(self._evented_attrs.values()):
            if self.ensure_events:
                lines.append("It ensures the event subscribtion "
                             "for all forwarded attributes:")
            else:
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


# Proxy metaclass
def FacadeMeta(name, bases, dct):
    """Metaclass for Facade device.

    Return a FacadeMeta instance.
    """
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
    return DeviceMeta(name, bases, dct)
