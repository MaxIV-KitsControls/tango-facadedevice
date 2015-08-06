"""Provide generic decorators."""

# Imports
import sys
import time
import PyTango
from collections import deque
from functools import wraps, partial
from weakref import WeakKeyDictionary
from collections import MutableMapping, namedtuple
from PyTango import AttrQuality, AttReqType, server

# Constants
ATTR_NOT_ALLOWED = "API_AttrNotAllowed"

# Stamped tuple
_stamped = namedtuple("stamped", ("value", "stamp", "quality"))
stamped = partial(_stamped, quality=AttrQuality.ATTR_VALID)


# Read attributes helper
def read_attributes(proxy, attributes):
    """Modified version of DeviceProxy.read_attribute."""
    result = proxy.read_attributes(attributes)
    for attr, res in zip(attributes, result):
        if not res.has_failed:
            continue
        try:
            proxy.read_attribute(attr)
        except PyTango.DevFailed as exc:
            if exc[0].reason != ATTR_NOT_ALLOWED:
                raise
    return result


# Tango objects
def is_tango_object(arg):
    """Return tango data if the argument is a tango object,
    False otherwise.
    """
    classes = server.attribute, server.device_property
    if isinstance(arg, classes):
        return arg
    try:
        return arg.__tango_command__
    except AttributeError:
        return False


# Run server class method
@classmethod
def run_server(cls, args=None, **kwargs):
    """Run the class as a device server.
    It is based on the PyTango.server.run method.

    The difference is that the device class
    and server name are automatically given.

    Args:
        args (iterable): args as given in the PyTango.server.run method
                         without the server name. If None, the sys.argv
                         list is used
        kwargs: the other keywords argument are as given
                in the PyTango.server.run method.
    """
    if not args:
        args = sys.argv[1:]
    args = [cls.__name__] + list(args)
    return server.run((cls,), args, **kwargs)


# DeviceMeta metaclass
def DeviceMeta(name, bases, attrs):
    """Enhanced version of PyTango.server.DeviceMeta
    that supports inheritance.
    """
    # Attribute dictionary
    dct = {"run_server": run_server}
    # Filter object from bases
    bases = tuple(base for base in bases if base != object)
    # Add device to bases
    if PyTango.server.Device not in bases:
        bases += (PyTango.server.Device,)
    # Set tango objects as attributes
    for base in reversed(bases):
        for key, value in base.__dict__.items():
            if is_tango_object(value):
                dct[key] = value
    # Update attribute dictionary
    dct.update(attrs)
    # Create device class
    cls = PyTango.server.DeviceMeta(name, bases, dct)
    cls.TangoClassName = name
    return cls


# Catch KeyError decorator
def catch_key_error(func=None, dtype=int):
    """Return a decorator to catch index errors."""
    def decorator(func):
        """Decorator to catch index erros."""
        @wraps(func)
        def wrapper(self):
            """Wrapper for attribute reader."""
            try:
                return func(self)
            except KeyError:
                quality = PyTango.AttrQuality.ATTR_INVALID
                return dtype(), time.time(), quality
        return wrapper
    # Decorate
    if func:
        return decorator(func)
    # Or return decorator
    return decorator


# Cache decorator
def cache_during(timeout_attr, debug_stream=None):
    """Decorator to cache a result during an amount of time
    defined by a given attribute name.
    """
    cache = WeakKeyDictionary()

    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            # Get debug stream
            func_name = func.__name__
            if debug_stream:
                stream = getattr(self, debug_stream)
            else:
                stream = lambda msg: None
            # Get stamps and value
            timeout = getattr(self, timeout_attr)
            queue, value = cache.get(self, (deque(maxlen=10), None))
            stamp = queue[-1] if queue else -timeout
            now = time.time()
            # Log periodicity
            if len(queue):
                msg = "{0} ran {1} times in the last {2:1.3f} seconds"
                stream(msg.format(func_name, len(queue),
                                  time.time() - queue[0]))
            # Use cache
            if stamp + timeout > now:
                msg = "{0} called before expiration ({1:1.3f} s < {2:1.3f} s)"
                stream(msg.format(func_name, now - stamp, timeout))
                return value
            # Call original method
            value = func(self, *args, **kwargs)
            msg = "{0} ran in {1:1.3f} seconds"
            stream(msg.format(func_name, time.time() - now))
            # Save cache and stamp
            queue.append(now)
            cache[self] = queue, value
            # Return
            return value
        # Create cache access
        wrapper.pop_cache = lambda arg: cache.pop(arg, None)
        return wrapper
    return decorator


# Event property
class event_property(object):
    """Property that pushes change events automatically."""

    # Aliases
    INVALID = AttrQuality.ATTR_INVALID
    VALID = AttrQuality.ATTR_VALID

    def __init__(self, attribute, default=None, invalid=None,
                 is_allowed=None, event=True, dtype=None, doc=None):
        self.attribute = attribute
        self.default = default
        self.invalid = invalid
        self.event = event
        self.dtype = dtype if callable(dtype) else None
        self.__doc__ = doc
        default = getattr(attribute, "is_allowed_name", "")
        self.is_allowed = is_allowed or default

    # Helper

    def get_attribute_name(self):
        try:
            return self.attribute.attr_name
        except AttributeError:
            return self.attribute

    def get_is_allowed_method(self, device):
        if callable(self.is_allowed):
            return self.is_allowed
        if self.is_allowed:
            return getattr(device, self.is_allowed)
        name = "is_" + self.get_attribute_name() + "_allowed"
        return getattr(device, name, None)

    def allowed(self, device):
        is_allowed = self.get_is_allowed_method(device)
        return not is_allowed or is_allowed(AttReqType.READ_REQ)

    def event_enabled(self, device):
        if self.event and isinstance(self.event, basestring):
            return getattr(device, self.event)
        return self.event

    def get_private_value(self, device):
        name = "__" + self.get_attribute_name() + "_value"
        return getattr(device, name)

    def set_private_value(self, device, value):
        name = "__" + self.get_attribute_name() + "_value"
        setattr(device, name, value)

    def get_private_quality(self, device):
        name = "__" + self.get_attribute_name() + "_quality"
        return getattr(device, name)

    def set_private_quality(self, device, quality):
        name = "__" + self.get_attribute_name() + "_quality"
        setattr(device, name, quality)

    def get_private_stamp(self, device):
        name = "__" + self.get_attribute_name() + "_stamp"
        return getattr(device, name)

    def set_private_stamp(self, device, stamp):
        name = "__" + self.get_attribute_name() + "_stamp"
        setattr(device, name, stamp)

    def delete_all(self, device):
        for suffix in ("_value", "_stamp", "_quality"):
            name = "__" + self.get_attribute_name() + suffix
            try:
                delattr(device, name)
            except AttributeError:
                pass

    @staticmethod
    def unpack(value):
        try:
            value.stamp = value.time.totime()
        except AttributeError:
            pass
        try:
            return value.value, value.stamp, value.quality
        except AttributeError:
            pass
        try:
            return value.value, value.stamp, None
        except AttributeError:
            pass
        try:
            return value.value, None, value.quality
        except AttributeError:
            pass
        return value, None, None

    def check_value(self, device, value, stamp, quality):
        if value in (None, self.invalid):
            return self.get_default_value(device), stamp, self.INVALID
        if self.dtype:
            value = self.dtype(value)
        return value, stamp, quality

    def get_default_value(self, device):
        if self.default != self.invalid:
            return self.default
        if self.dtype:
            return self.dtype()
        attr = getattr(device, self.get_attribute_name())
        if attr.get_data_type() == PyTango.DevString:
            return str()
        if attr.get_max_dim_x() > 1:
            return list()
        return int()

    def get_default_quality(self):
        if self.default != self.invalid:
            return self.VALID
        return self.INVALID

    # Descriptors

    def __get__(self, instance, owner=None):
        if instance is None:
            return self
        return self.getter(instance)

    def __set__(self, instance, value):
        return self.setter(instance, value)

    def __delete__(self, instance):
        return self.deleter(instance)

    # Access methods

    def getter(self, device):
        if not self.allowed(device):
            self.set_value(device, quality=self.INVALID)
        value, stamp, quality = self.get_value(device)
        if quality == self.INVALID:
            return self.invalid
        return value

    def setter(self, device, value):
        value, stamp, quality = self.unpack(value)
        if not self.allowed(device):
            quality = self.INVALID
        args = device, value, stamp, quality
        self.set_value(device, *self.check_value(*args))

    def deleter(self, device):
        self.reloader(device)

    def reloader(self, device=None, reset=True):
        # Prevent class calls
        if device is None:
            return
        # Delete attributes
        if reset:
            self.delete_all(device)
        # Set quality
        if not self.allowed(device):
            self.set_value(device, quality=self.INVALID,
                           disable_event=reset)
        # Force events
        if reset and self.event_enabled(device):
            self.push_event(device, *self.get_value(device))

    # Private attribute access

    def get_value(self, device, attr=None):
        try:
            value = self.get_private_value(device)
            stamp = self.get_private_stamp(device)
            quality = self.get_private_quality(device)
        except AttributeError:
            value = self.get_default_value(device)
            stamp = time.time()
            quality = self.get_default_quality()
        if attr:
            attr.set_value_date_quality(value, stamp, quality)
        return value, stamp, quality

    def set_value(self, device, value=None, stamp=None, quality=None,
                  disable_event=False):
        # Prepare
        old_value, old_stamp, old_quality = self.get_value(device)
        if value is None:
            value = old_value
        if stamp is None:
            stamp = time.time()
        if quality is None and value is not None:
            quality = self.VALID
        elif quality is None:
            quality = old_quality
        # Test differences
        diff = old_quality != quality or old_value != value
        try:
            bool(diff)
        except ValueError:
            diff = diff.any()
        if not diff:
            return
        # Set
        self.set_private_value(device, value)
        self.set_private_stamp(device, stamp)
        self.set_private_quality(device, quality)
        # Push event
        if not disable_event and self.event_enabled(device):
            self.push_event(device, *self.get_value(device))

    # Aliases

    read = get_value
    write = set_value

    # Event method

    def push_event(self, device, value, stamp, quality):
        attr = getattr(device, self.get_attribute_name())
        if not attr.is_change_event():
            attr.set_change_event(True, False)
        device.push_change_event(self.get_attribute_name(),
                                 value, stamp, quality)


# Mapping object
class mapping(MutableMapping):
    """Mapping object to gather python attributes."""

    def clear(self):
        for x in self:
            del self[x]

    def __init__(self, instance, convert, keys):
        self.key_list = list(keys)
        self.convert = convert
        self.instance = instance

    def __getitem__(self, key):
        if key not in self.key_list:
            raise KeyError(key)
        return getattr(self.instance, self.convert(key))

    def __setitem__(self, key, value):
        if key not in self.key_list:
            raise KeyError(key)
        setattr(self.instance, self.convert(key), value)

    def __delitem__(self, key):
        if key not in self.key_list:
            raise KeyError(key)
        delattr(self.instance, self.convert(key))

    def __iter__(self):
        return iter(self.key_list)

    def __len__(self):
        return len(self.key_list)

    def __str__(self):
        return str(dict(self.items()))

    def __repr__(self):
        return repr(dict(self.items()))
