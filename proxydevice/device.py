"""Provide the proxy device class and metaclass"""

# Imports
from contextlib import contextmanager
from proxydevice.objects import proxy_object

# PyTango
from PyTango.server import Device, DeviceMeta
from PyTango import DeviceProxy, DevFailed, DevState


# Proxy device
class Proxy(Device):
    """Provide base methods for a proxy device."""

    @contextmanager
    def safe_context(self, exceptions, msg=""):
        """Catch errors and set the device to FAULT
        with a corresponding status.
        """
        try: yield
        except exceptions as exc:
            self._proxy_data = {}
            self.set_state(DevState.FAULT)
            exc = str(exc) if str(exc) else repr(exc)
            args = filter(None, [msg.capitalize(), exc.capitalize()])
            self.set_status('\n'.join(args))

    @property
    def connected(self):
        """True if all the proxies are connected, False otherwise."""
        return bool(self._proxy_data)

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
        # Handle properties
        with self.safe_context((TypeError, ValueError, KeyError)):
            self.get_device_properties()
        # Init attributes
        self._proxy_data = {}
        self._proxy_attribute_dct = {}
        self._proxy_device_dct = {}
        # Invalid property case
        if self.get_state() != DevState.INIT:
            return
        # Get properties
        for key, value in self._proxy_property_dct.items():
            proxy = getattr(self, key.lower())
            attributes = [(attr, getattr(self, prop.lower()), dtype)
                          for attr, prop, dtype in value]
            self._proxy_attribute_dct[proxy] = sorted(attributes)
        self._proxy_device_dct = dict.fromkeys(self._proxy_attribute_dct)
        # First update
        self.read_attr_hardware()

    def read_attr_hardware(self, attr=None):
        """Update the device."""
        # Connection error
        if not self.connected and self.get_state() == DevState.FAULT:
            return
        # Try to access the proxy
        msg = "Cannot connect to proxy."
        with self.safe_context((DevFailed), msg):
            # Connect to proxies
            for key, value in self._proxy_device_dct.items():
                if not value:
                    self._proxy_device_dct[key] = DeviceProxy(key)
            # Read data
            for key, values in self._proxy_attribute_dct.items():
                # Unpack
                tag_names =  [tag   for attr, tag, dtype in values]
                attr_names = [attr  for attr, tag, dtype in values]
                dtypes =     [dtype for attr, tag, dtype in values]
                # Read attributes
                device = self._proxy_device_dct[key]
                values = device.read_attributes(tag_names)
                # Store data
                for attr, dtype, value in zip(attr_names, dtypes, values):
                    self._proxy_data[attr] = dtype(value.value)
            # Update data
            for attr, method in self._proxy_method_dct.items():
                self._proxy_data[attr] = method(self, self._proxy_data)
            # Set state
            state = self.state_from_data(self._proxy_data)
            if state is not None:
                self.set_state(state)
            # Set status
            status = self.status_from_data(self._proxy_data)
            if status is not None:
                self.set_status(status)

    def state_from_data(self, data):
        """Method to override."""
        return None

    def status_from_data(self, data):
        """Method to override."""
        return None


# Forwarder metaclass
def ProxyMeta(name, bases, dct):
    """Metaclass for Proxy device.

    Return a DeviceMeta instance.
    """
    # Class attribute
    dct["_proxy_property_dct"] = {}
    dct["_proxy_method_dct"] = {}
    # Proxy objects
    for key, value in dct.items():
        if isinstance(value, proxy_object):
            value.update_class(key, dct)
    # Create device class
    return DeviceMeta(name, bases, dct)

