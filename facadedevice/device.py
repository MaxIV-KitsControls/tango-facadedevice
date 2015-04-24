"""Provide the facade device class and metaclass"""

# Imports
import traceback
from threading import Lock
from functools import partial
from collections import defaultdict
from contextlib import contextmanager
from facadedevice.objects import class_object, attribute_mapping
from facadedevice.common import DeviceMeta, cache_during

# PyTango
from PyTango.server import Device, device_property, command
from PyTango import DeviceProxy, DevFailed, DevState, EventType, EventData


# Proxy device
class Facade(Device):
    """Provide base methods for a facade device."""
    __metaclass__ = DeviceMeta

    @contextmanager
    def safe_context(self, exceptions, msg=""):
        """Catch errors and set the device to FAULT
        with a corresponding status.
        """
        try:
            yield
        except exceptions as exc:
            self.register_exception(exc, msg)

    def register_exception(self, exc, msg=""):
        self._exception = exc
        self._data_dict.clear()
        exc = str(exc) if str(exc) else repr(exc)
        form = lambda x: x[0].capitalize() + x[1:] if x else x
        args = filter(None, [form(msg), form(exc)])
        self.set_state(DevState.FAULT)
        self.set_status('\n'.join(args))
        self.debug_stream(traceback.format_exc().replace("%", "%%"))

    def get_device_properties(self, cls=None):
        """Raise a ValueError if a property is missing."""
        Device.get_device_properties(self, cls)
        for key, value in self.device_property_list.items():
            if value[2] is None:
                raise ValueError('missing property: ' + key)

    def configure_events(self):
        """Configure events and update period from property."""
        self.use_events = self.UseEvents
        if self.use_events:
            self.update_period = 0
            ms = int(1000 * self.UpdatePeriod)
            self.poll_command("Update", ms)
            return
        self.update_period = self.UpdatePeriod
        try:
            self.stop_poll_command("Update")
        except DevFailed as exc:
            self.debug_stream(str(exc))

    def init_device(self):
        """Initialize the device."""
        # Initialize state
        self.set_state(DevState.INIT)
        # Init attributes
        self._lock = Lock()
        self._tmp_dict = {}
        self._exception = None
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
        # First update
        self.update_all()

    def delete_device(self):
        for proxy, attrs in self._evented_attrs.items():
            for attr, eid in attrs.items():
                try:
                    proxy.unsubscribe_event(eid)
                except Exception as exc:
                    self.debug_stream(str(exc))

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

    def listen_to_attributes(self, proxy, attr_dict):
        "Try to setup event listeners for the attributes on a proxy"
        for attr, attr_proxy in attr_dict.items():
            try:
                eid = proxy.subscribe_event(
                    attr_proxy,
                    EventType.CHANGE_EVENT,
                    partial(self.on_change_event, attr))
            except DevFailed:
                msg = "Can't subscribe to change event for attribute {0}/{1}"
                self.debug_stream(msg.format(proxy.dev_name(), attr))
            else:
                self._evented_attrs[proxy][attr_proxy] = eid
                msg = "Subscribed to change event for attribute {0}/{1}"
                self.debug_stream(msg.format(proxy.dev_name(), attr))

    def on_change_event(self, attr, event):
        "Handle attribute change events"
        # Ignore the event if not a data event
        if not isinstance(event, EventData):
            msg = "Not a data event:\n{0}"
            self.warn_stream(msg.format(event))
            return
        # Ignore the event if it contains an error
        if event.err:
            msg = "Event contains errors:\n{0}"
            self.warn_stream(msg.format(event))
            return
        # Save and update
        self._data_dict[attr] = event.attr_value
        self.local_update()

    @cache_during("update_period", "debug_stream")
    def remote_update(self):
        """Update the attributes by reading from the proxies."""
        # Connection error
        if self._exception:
            return
        # Try to access the proxy
        new_proxies = set()
        msg = "Cannot connect to proxy."
        with self.safe_context((DevFailed), msg):
            # Connect to proxies
            for device in self._device_dict.values():
                if device not in self._proxy_dict:
                    proxy = DeviceProxy(device)
                    new_proxies.add(proxy)
                    self._proxy_dict[device] = proxy
                    self._evented_attrs[proxy] = {}
            # Read data
            for device, attr_dict in self._read_dict.items():
                proxy = self._proxy_dict[device]
                # Filter attribute dict
                polled = dict((attr, attr_proxy)
                              for attr, attr_proxy in attr_dict.items()
                              if attr_proxy not in self._evented_attrs[proxy])
                # Read attributes
                values = polled and proxy.read_attributes(polled.values())
                # Store data
                for attr, value in zip(polled, values):
                    self._data_dict[attr] = value
                # Setup listeners
                if proxy in new_proxies:
                    self.listen_to_attributes(proxy, attr_dict)

    def local_update(self):
        """Update logical attributes, state and status."""
        # Connection error
        if self._exception:
            return
        with self._lock:
            # Update data
            for key, method in self._method_dict.items():
                self._data_dict[key] = method(self._data_dict)
            # Set state
            state = self.state_from_data(self._data_dict)
            if state is not None:
                self.set_state(state)
            # Set status
            status = self.status_from_data(self._data_dict)
            if status is not None:
                self.set_status(status)

    def update_all(self):
        """Update all."""
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
        return self._device_dict

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
        if not self.use_events:
            self.update_all()

    def dev_state(self):
        """Update attributes and return the state."""
        if not self.use_events:
            self.update_all()
        return Device.dev_state(self)

    # Device properties

    UpdatePeriod = device_property(
        dtype=float,
        doc="Set the refresh rate for polled attributes.",
        default_value=1.0,
        )

    UseEvents = device_property(
        dtype=bool,
        doc="Enable change events for all attributes.",
        default_value=False,
        )

    # Commands

    @command
    def Update(self):
        self.update_all()


# Proxy metaclass
def FacadeMeta(name, bases, dct):
    """Metaclass for Facade device.

    Return a FacadeMeta instance.
    """
    # Class attribute
    dct["_class_dict"] = {"attributes": {},
                          "commands":   {},
                          "devices":    {}}
    # Proxy objects
    for key, value in dct.items():
        if isinstance(value, class_object):
            value.update_class(key, dct)
    # Create device class
    return DeviceMeta(name, bases, dct)
