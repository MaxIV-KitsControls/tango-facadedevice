"""Provide helpers for exception handling."""

# Imports

import sys
import traceback
from contextlib import contextmanager

from tango import DevFailed, Except


# Safe traceback string

def traceback_string(exc, limit=None):
    if getattr(exc, '__traceback__', None):
        return ''.join(traceback.format_tb(exc.__traceback__, limit=limit))
    if any(sys.exc_info()):
        return traceback.format_exc(limit=limit)
    return ''


# Safe exception representation

def exception_string(exc, wrap=None):
    # Convert DevFailed
    if isinstance(exc, DevFailed) and exc.args:
        exc = exc.args[0]
    # Exception as a string
    try:
        base = exc.desc
    except AttributeError:
        base = str(exc) if str(exc) else repr(exc)
    # No wrapping
    if not wrap:
        return base
    # Wrapping
    indented = '\n'.join('  ' + line for line in base.splitlines())
    return "{}:\n{}".format(wrap, indented)


# DevFailed conversion

def to_dev_failed(exc):
    tb = traceback_string(exc)
    desc = exception_string(exc)
    try:
        Except.throw_exception('PyDs_PythonError', desc, tb)
    except Exception as exc:
        return exc


# Exception context

class ContextException(Exception):

    def __init__(self, base, context, origin, traceback):
        super(ContextException, self).__init__(base, context, origin)
        self.base = base
        self.context = context
        self.origin = origin
        self.__traceback__ = traceback

    @property
    def desc(self):
        wrap = "Exception while {} {}".format(self.context, self.origin)
        return exception_string(self.base, wrap)

    def __str__(self):
        return self.desc


# Exception context manager

@contextmanager
def context(msg, origin):
    try:
        yield
    except Exception as exc:
        _, _, tb = sys.exc_info()
        raise ContextException(
            exc, msg, origin, tb)
