"""Provide generic decorators."""

# Imports
import time
import ctypes
import weakref
import threading
import functools
import itertools
import traceback
import collections

# PyTango imports
import PyTango
from PyTango import server
from PyTango.server import DeviceMeta
from PyTango import AttrQuality, AttReqType, AttrWriteType, DevFailed

# Numpy print options
try:
    import numpy
    numpy.set_printoptions(precision=5, threshold=6)
except Exception:
    print("Couldn't customize numpy print options")

# Constants
ATTR_NOT_ALLOWED = "API_AttrNotAllowed"
NONE_STRING = "none"

# Stamped tuple
stamped = collections.namedtuple("stamped", ("value", "stamp", "quality"))
stamped.__new__.__defaults__ = (AttrQuality.ATTR_VALID,)


# TID helper
def gettid():
    libc = 'libc.so.6'
    for cmd in (186, 224, 178):
        try:
            tid = ctypes.CDLL(libc).syscall(cmd)
        except OSError:
            return threading.current_thread().ident
        if tid != -1:
            return tid


# Safer traceback
def safe_traceback(limit=None):
    return traceback.format_exc(limit=limit).replace("%", "%%")


# Debug it decorator
def debug_it(func):
    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        # Enter method
        tid = gettid()
        method = func.__name__
        msg = "Entering method {0} (tid={1})"
        self.debug_stream(msg.format(method, tid))
        # Run method
        try:
            result = func(self, *args, **kwargs)
        # Exit method with exception
        except Exception as exception:
            msg = "Method {0} failed (exception={1!r}, tid={2})"
            self.debug_stream(msg.format(method, exception, tid))
            raise
        # Exit method with result
        else:
            msg = "Method {0} returned (result={1!r}, tid={2})"
            self.debug_stream(msg.format(method, result, tid))
            return result
    return wrapper


# Patched device proxy
def create_device_proxy(*args, **kwargs):
    proxy = PyTango.DeviceProxy(*args, **kwargs)
    proxy._get_info_()
    return proxy


# Read attributes helper
def read_attributes(proxy, attributes):
    """Modified version of DeviceProxy.read_attribute."""
    attributes = map(str.strip, map(str.lower, attributes))
    attrs = list(set(attributes))
    result = proxy.read_attributes(attrs)
    for attr, res in zip(attrs, result):
        if not res.has_failed:
            continue
        try:
            proxy.read_attribute(attr)
        except PyTango.DevFailed as exc:
            if exc[0].reason != ATTR_NOT_ALLOWED:
                raise
    mapping = dict(zip(attrs, result))
    return [mapping[attr] for attr in attributes]


def is_writable_attribute(attr_name, device_proxy):
    """ Return if tango attribute exists and is writable, and also return
     string description """
    desc = "Attribute {0}/{1} is writable"
    writable = True
    try:
        # get attribute configuration
        cfg = device_proxy.get_attribute_config(attr_name)
        if cfg.writable is AttrWriteType.READ:
            # attribute exists but it is not writable
            desc = "Attribute {0}/{1} is not writable"
            writable = False
    except DevFailed:
        # attribute doesn't exist
        desc = "Can't find attribute {0}/{1} "
        writable = False
    desc = desc.format(device_proxy.name(), attr_name)
    return writable, desc


def tangocmd_exist(cmd_name, device_proxy):
    """ Return if tango command exist and return string description."""
    desc = "Command {0}/{1} exists"
    cmd_exists = True
    try:
        # check command description
        device_proxy.command_query(cmd_name)
    except DevFailed:
        # command_query failed, command doesn't exist
        desc += "-Command {0}/{1} doesn't exist'\n"
        cmd_exists = False
    desc = desc.format(device_proxy.name(), cmd_name)
    return cmd_exists, desc


# Device class
class Device(server.Device):
    """Enhanced version of server.Device"""
    __metaclass__ = DeviceMeta

    def init_device(self):
        self.__event_dict = {}
        self.__eid_counter = itertools.count(1)
        super(Device, self).init_device()

    def __wrap_callback(self, callback, eid):
        def wrapped(event):
            with PyTango.AutoTangoMonitor(self):
                if eid in self.__event_dict:
                    callback(event)
        return wrapped

    def subscribe_event(self, attr_name, event_type, callback,
                        filters=[], stateless=False, proxy=None):
        # Get proxy
        if proxy is None:
            device_name = '/'.join(attr_name.split('/')[:-1])
            attr_name = attr_name.split('/')[-1]
            proxy = PyTango.device_proxy(device_name)
        # Create callback
        eid = next(self.__eid_counter)
        self.__event_dict[eid] = proxy, attr_name, None
        wrapped = self.__wrap_callback(callback, eid)
        # Subscribe
        try:
            proxy_eid = proxy.subscribe_event(
                attr_name, event_type, wrapped, filters, stateless)
        # Error
        except Exception:
            del self.__event_dict[eid]
            raise
        # Success
        self.__event_dict[eid] = proxy, attr_name, proxy_eid
        return eid

    def unsubscribe_event(self, eid):
        proxy, attr_name, proxy_eid = self.__event_dict.pop(eid)
        proxy.unsubscribe_event(proxy_eid)

    def delete_device(self):
        # Unsubscribe from all attributes
        for eid in list(self.__event_dict):
            proxy, attr_name, proxy_eid = self.__event_dict[eid]
            attr_name = '/'.join((proxy.dev_name(), attr_name))
            try:
                proxy.unsubscribe_event(proxy_eid)
            except Exception as exc:
                msg = "Cannot unsubscribe from attribute {0}: {1!r}"
                msg = msg.format(attr_name, exc)
                self.error_stream(msg)
            else:
                msg = "Successfully Unsubscribed from attribute {0}"
                msg = msg.format(attr_name)
                self.info_stream(msg)
        # Call parent
        super(Device, self).delete_device()


# Catch KeyError decorator
def catch_key_error(func=None, dtype=int):
    """Return a decorator to catch index errors."""
    def decorator(func):
        """Decorator to catch index erros."""
        @functools.wraps(func)
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
    def decorator(func):
        cache = weakref.WeakKeyDictionary()

        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            # Get debug stream
            func_name = func.__name__
            if debug_stream:
                stream = getattr(self, debug_stream)
            else:
                stream = lambda msg: None
            # Get stamps and value
            timeout = getattr(self, timeout_attr)
            defaults = collections.deque(maxlen=10), None
            queue, value = cache.get(self, defaults)
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
                 is_allowed=None, event=True, dtype=None,
                 callback=None, errback=None, doc=None):
        self.attribute = attribute
        self.default = default
        self.invalid = invalid
        self.callback = callback
        self.errback = errback
        self.event = event
        self.dtype = dtype if callable(dtype) else None
        self.__doc__ = doc
        default = getattr(attribute, "is_allowed_name", "")
        self.is_allowed = is_allowed or default

    # Helper

    def debug_stream(self, device, action, value):
        if not getattr(device, 'HeavyLogging', False):
            return
        action = action.capitalize()
        attr = self.get_attribute_name()
        msg = "{0} event property for attribute {1} (value={2!r}, tid={3})"
        device.debug_stream(msg.format(action, attr, value, gettid()))

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

    def notify(self, device, args, err=False):
        callback = self.errback if err else self.callback
        if not callback:
            return
        # Prepare callback
        if isinstance(callback, basestring):
            callback = getattr(device, callback, None)
        else:
            callback = functools.partial(callback, device)
        # Run callback
        try:
            callback(*args)
        # Handle exception
        except Exception as exc:
            # Message formatting
            origin = self.get_attribute_name()
            name = "error callback" if err else "callback"
            msg = "Exception while running {0} for attribute {1}: {2!r}"
            msg = msg.format(name, origin, exc)
            # Use errback
            if not err and self.errback:
                self.notify(device, (exc, msg, origin), err=True)
            # Default handling
            else:
                device.error_stream(msg)
                device.debug_stream(safe_traceback())

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
        if value is None or \
           (self.invalid is not None and value == self.invalid):
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
            self.push_events(device, *self.get_value(device))

    # Private attribute access

    def get_value(self, device, attr=None):
        # Get value
        try:
            value = self.get_private_value(device)
            stamp = self.get_private_stamp(device)
            quality = self.get_private_quality(device)
        except AttributeError:
            value = self.get_default_value(device)
            stamp = time.time()
            quality = self.get_default_quality()
        # Set value
        if attr:
            attr.set_value_date_quality(value, stamp, quality)
        # Stream
        self.debug_stream(device, 'getting', value)
        # Return
        return stamped(value, stamp, quality)

    def set_value(self, device, value=None, stamp=None, quality=None,
                  disable_event=False):
        self.debug_stream(device, 'setting', value)
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
        diff = (old_stamp != stamp or
                old_quality != quality or
                old_value != value)
        try:
            bool(diff)
        except ValueError:
            diff = diff.any()
        # No changes
        if not diff:
            return
        # Set the internals
        self.set_private_value(device, value)
        self.set_private_stamp(device, stamp)
        self.set_private_quality(device, quality)
        # Notify if necessary
        self.notify(device, (value, stamp, quality))
        # Push events
        if not disable_event and self.event_enabled(device):
            self.push_events(device, *self.get_value(device))

    # Aliases

    read = get_value
    write = set_value

    # Event methods

    def push_events(self, device, value, stamp, quality):
        attr_name = self.get_attribute_name()
        attr = getattr(device, attr_name)
        # Change events
        if not attr.is_change_event():
            attr.set_change_event(True, False)
        device.push_change_event(attr_name, value, stamp, quality)
        # Archive events
        if not attr.is_archive_event():
            # Enable verification of event properties
            attr.set_archive_event(True, True)
        device.push_archive_event(attr_name, value, stamp, quality)


# Mapping object
class mapping(collections.MutableMapping):
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
