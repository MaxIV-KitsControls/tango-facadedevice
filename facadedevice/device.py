"""Provide the facade device class and metaclass"""

# Imports
from threading import Lock
from functools import partial
from collections import defaultdict
from contextlib import contextmanager
from facadedevice.objects import class_object, attribute_mapping
from facadedevice.common import DeviceMeta, cache_during

# PyTango
from PyTango.server import Device, device_property, command
from PyTango import DeviceProxy, DevFailed, DevState, EventType


# Read dictionary generator
def gen_read_dict():
    """Generate a defaultdict of tuples containing 3 empty lists."""
    factory = lambda: tuple([] for _ in range(3))
    return defaultdict(factory)


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
            self._data_dict = {}
            self.set_state(DevState.FAULT)
            exc = str(exc) if str(exc) else repr(exc)
            form = lambda x: x[0].capitalize() + x[1:] if x else x
            args = filter(None, [form(msg), form(exc)])
            self.set_status('\n'.join(args))

    def get_device_properties(self, cls=None):
        """Raise a ValueError if a property is missing."""
        Device.get_device_properties(self, cls)
        for key, value in self.device_property_list.items():
            if value[2] is None:
                raise ValueError('missing property: ' + key)

    def init_device(self):
        """Initialize the device."""
        # Initialize state
        self.set_state(DevState.INIT)
        # Init attributes
        self.lock = Lock()
        self._tmp_dict = {}
        self._device_dict = {}
        self._method_dict = {}
        self._command_dict = {}
        self._evented_attrs = {}
        self._attribute_dict = {}
        self._read_dict = gen_read_dict()
        self._data_dict = attribute_mapping(self)
        # Handle properties
        with self.safe_context((TypeError, ValueError, KeyError)):
            self.get_device_properties()
            self.poll_command("Update", int(1000 * self.UpdatePeriod))
        # Invalid property case
        if self.get_state() != DevState.INIT:
            return
        # Data structure
        self.init_data_structure()
        # First update
        self.remote_update()
        self.local_update()

    def delete_device(self):
        for attr, eid in self._evented_attrs.items():
            try:
                proxy = self._device_dict[attr]
                proxy.unsubscribe_event(eid)
            except Exception as exc:
                self.debug_stream(str(exc))

    def init_data_structure(self):
        """Initialize the internal data structures."""
        # Get informations for proxies
        for key, value in self._class_dict["devices"].items():
            proxy_name = getattr(self, value.device)
            self._device_dict[key] = proxy_name
        # Get informations for attributes
        for key, value in sorted(self._class_dict["attributes"].items()):
            if value.attr and value.device:
                attr = getattr(self, value.attr)
                self._attribute_dict[key] = attr, value.dtype
                self._read_dict[value.device][0].append(key)
                self._read_dict[value.device][1].append(attr)
                self._read_dict[value.device][2].append(value.dtype)
            if value.method:
                self._method_dict[key] = value.method.__get__(self)
        # Get informations for commands
        for key, value in self._class_dict["commands"].items():
            attr = getattr(self, value.attr)
            self._command_dict[key] = (attr, value.value, value.reset_value,
                                       value.reset_delay)

    def listen_to_attributes(self, proxy, keys, attrs, dtypes):
        "Try to setup event listeners for the attributes on a proxy"
        for key, attr, dtype in zip(keys, attrs, dtypes):
            try:
                eid = proxy.subscribe_event(
                    attr, EventType.CHANGE_EVENT,
                    partial(self.handle_change_event, key, dtype))
            except DevFailed:
                msg = "Can't subscribe to change event for attribute {0}/{1}"
                self.debug_stream(msg.format(proxy.dev_name(), attr))
            else:
                self._evented_attrs[attr] = eid
                msg = "Subscribed to change event for attribute {0}/{1}"
                self.debug_stream(msg.format(proxy.dev_name(), attr))

    def handle_change_event(self, attr, dtype, event):
        "Handle attribute change events"
        data = event.attr_value
        data.value = dtype(data.value)
        self._data_dict[attr] = data
        self.local_update()

    def remote_update(self):
        """Update the attributes by reading from the proxies."""
        # Connection error
        if not self.connected and self.get_state() == DevState.FAULT:
            return
        # Try to access the proxy
        new_proxies = set()
        msg = "Cannot connect to proxy."
        with self.safe_context((DevFailed), msg):
            # Connect to proxies
            for key, value in self._device_dict.items():
                if isinstance(value, basestring):
                    if value not in self._tmp_dict:
                        proxy = DeviceProxy(value)
                        new_proxies.add(proxy)
                        self._tmp_dict[value] = proxy
                    self._device_dict[key] = self._tmp_dict[value]
            # Read data
            for keys, attrs, dtypes in self._read_dict.values():
                device_proxy = self._device_dict[keys[0]]
                polled = [attr for attr in attrs
                          if attr not in self._evented_attrs]
                if polled:
                    values = device_proxy.read_attributes(polled)
                # Store data
                for key, dtype, value in zip(keys, dtypes, values):
                    value.value = dtype(value.value)
                    self._data_dict[key] = value
            # Setup listeners
            for device_proxy in new_proxies:
                self.listen_to_attributes(device_proxy, keys, attrs, dtypes)

    def local_update(self):
        """Update logical attributes, state and status."""
        with self.lock:
            # Connection error
            if not self.connected and self.get_state() == DevState.FAULT:
                return
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

    # Properties

    @property
    def connected(self):
        """True if all the proxies are connected, False otherwise."""
        return self.get_state() != DevState.FAULT

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

    # Device properties

    UpdatePeriod = device_property(
        dtype=float,
        doc="Set the refresh rate for polled attributes.",
        default_value=1.0
        )

    # Commands

    @command
    def Update(self):
        self.remote_update()
        self.local_update()





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
