"""Provide generic decorators."""

# Imports
from time import time
from functools import wraps
from PyTango import AttrQuality


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
                return dtype(), time(), AttrQuality.ATTR_INVALID
        return wrapper
    # Decorate
    if func:
        return decorator(func)
    # Or return decorator
    return decorator
