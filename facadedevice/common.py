"""Provide generic decorators."""

# Imports
import time
import PyTango
from functools import wraps
from collections import deque
from weakref import WeakKeyDictionary


# DeviceMeta metaclass
def DeviceMeta(name, bases, attrs):
    """Enhanced version of PyTango.server.DeviceMeta
    that supports inheritance.
    """
    # Save current attrs
    save_key = '_save_attrs'
    dct = {save_key: attrs}
    # Filter object from bases
    filt = lambda arg: arg != object
    bases = tuple(filter(filt, bases))
    # Add device to bases
    if PyTango.server.Device not in bases:
        bases += (PyTango.server.Device,)
    # Update attribute dictionary
    for base in reversed(bases):
        dct.update(getattr(base, save_key, {}))
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
            if len(queue):
                msg = "{0} ran {1} times in the last {2:1.3f} seconds"
                stream(msg.format(func_name, len(queue),
                                  time.time() - queue[0]))
            # Return
            return value
        return wrapper
    return decorator
