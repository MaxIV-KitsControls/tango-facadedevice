"""Provide the facade device class and metaclass"""

# Imports
from collections import defaultdict
from contextlib import contextmanager
from facadedevice.objects import class_object

# PyTango
from PyTango.server import Device, DeviceMeta
from PyTango import DeviceProxy, DevFailed, DevState


# Read dictionary generator
def gen_read_dict():
    """Generate a defaultdict of tuples containing 3 empty lists."""
    factory = lambda: tuple([] for _ in range(3))
    return defaultdict(factory)


# Proxy device
class Facade(Device):
    """Provide base methods for a facade device."""

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
            args = filter(None, [msg.capitalize(), exc.capitalize()])
            self.set_status('\n'.join(args))

    def get_device_properties(self, cls=None):
        """Patch version of device properties.
        Set properties at instance level in lower case.
        """
        Device.get_device_properties(self, cls)
        for key, value in self.device_property_list.items():
            if value[2] is None:
                raise ValueError('missing property: ' + key)
            setattr(self, key.lower(), value[2])

    def init_device(self):
        """Initialize the device."""
        # Initialize state
        self.set_state(DevState.INIT)
        # Init attributes
        self._tmp_dict = {}
        self._data_dict = {}
        self._attribute_dict = {}
        self._device_dict = {}
        self._method_dict = {}
        self._command_dict = {}
        self._read_dict = gen_read_dict()
        # Handle properties
        with self.safe_context((TypeError, ValueError, KeyError)):
            self.get_device_properties()
        # Invalid property case
        if self.get_state() != DevState.INIT:
            return
        # Data structure
        self.init_data_structure()
        # First update
        self.update()

    def init_data_structure(self):
        """Initialize the internal data structures."""
        # Get informations for proxies
        for key, value in self._class_dict["devices"].items():
            proxy_name = getattr(self, value.device.lower())
            self._device_dict[key] = proxy_name
        # Get informations for attributes
        for key, value in sorted(self._class_dict["attributes"].items()):
            if value.attr and value.device:
                attr = getattr(self, value.attr.lower())
                self._attribute_dict[key] = attr, value.dtype
                self._read_dict[value.device][0].append(key)
                self._read_dict[value.device][1].append(attr)
                self._read_dict[value.device][2].append(value.dtype)
            if value.method:
                self._method_dict[key] = value.method.__get__(self)
        # Get informations for commands
        for key, value in self._class_dict["commands"].items():
            try:
                attr = getattr(self, value.attr.lower())
            except AttributeError:
                attr = None
            self._command_dict[key] = (attr, value.value, value.reset_value,
                                       value.reset_delay)

    def update(self):
        """Update the device."""
        # Connection error
        if not self.connected and self.get_state() == DevState.FAULT:
            return
        # Try to access the proxy
        msg = "Cannot connect to proxy."
        with self.safe_context((DevFailed), msg):
            # Connect to proxies
            for key, value in self._device_dict.items():
                if isinstance(value, basestring):
                    proxy = self._tmp_dict.get(value) or DeviceProxy(value)
                    self._device_dict[key] = self._tmp_dict[value] = proxy
            # Read data
            for lists in self._read_dict.values():
                keys, attrs, dtypes = lists
                device_proxy = self._device_dict[keys[0]]
                values = device_proxy.read_attributes(attrs)
                # Store data
                for key, dtype, value in zip(keys, dtypes, values):
                    self._data_dict[key] = dtype(value.value)
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

    # Update device

    def read_attr_hardware(self, attr):
        """Update attributes."""
        self.update()

    def dev_state(self):
        """Update attributes and return the state."""
        self.update()
        return Device.dev_state(self)

    # Method to override

    def state_from_data(self, data):
        """Method to override."""
        return None

    def status_from_data(self, data):
        """Method to override."""
        return None


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
