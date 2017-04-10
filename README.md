tango-facadedevice
==================

[![Build Status](https://travis-ci.org/MaxIV-KitsControls/tango-facadedevice.svg?branch=master)](https://travis-ci.org/MaxIV-KitsControls/tango-facadedevice)
[![Coverage Status](https://coveralls.io/repos/github/MaxIV-KitsControls/tango-facadedevice/badge.svg?branch=master)](https://coveralls.io/github/MaxIV-KitsControls/tango-facadedevice?branch=master)

Provide reactive facade devices to subclass.

Information
-----------

 - Package: facadedevice
 - Device:  Facade (+ TimedFacade)
 - Repo:    [tango-facadedevice][repo]

[repo]: https://github.com/MaxIV-KitsControls/tango-facadedevice.git

Requirements
------------

The library requires:

 - python >= 2.7 or >= 3.4
 - pytango >= 9.2.1

The unit-tests require:

 - pytest-runner
 - pytest-mock
 - pytest-xdist
 - pytest-coverage


Usage
-----

The facade devices support the following objects:

- **local_attribute**: tango attribute holding a local value. Useful for
configuring the device at runtime.

- **logical_attribute**: tango attribute computed from the values of other
  attributes. Use it as a decorator to register the function that make this
  computation.

- **state_attribute**: It is used to describe the logical relationship between
  state/status and the other attributes. It is very similar to logical attributes.

- **proxy_attribute**: tango attribute bound to the attribute of a remote
  device. Full attribute name is given as property. It supports the
  standard attribute keywords. Optionally, a conversion method can be given.

- **combined_attribute**: tango attribute computed from the values of other
  remote attributes. Use it as a decorator to register the function that make
  this computation. The remote attribute names are provided by a property,
  either as a list or a pattern.

- **proxy_command**: TANGO command to write an attribute of a remote device
  with a given value. The full attribute name is given as a property. It
  supports standard command keywords.

Moreover, the `Facade` device is fully subclassable in a standard pythonic way
(super, calls to parent methods, etc).

The `TimedFacade` class already implement a `Time` attribute that can be used
to run periodic update (by binding to a logical attribute).


Example
-------

A real-world example used at MAX-IV:

```python
from facadedevice import Facade, proxy_command
from facadedevice import proxy_attribute, logical_attribute, state_attribute


class CameraScreen(Facade):

    # Proxy attributes

    StatusIn = proxy_attribute(
        dtype=bool,
        property_name="StatusInAttribute")

    StatusOut = proxy_attribute(
        dtype=bool,
        property_name="StatusOutAttribute")

    # Logical attributes

    @logical_attribute(
        dtype=bool,
        bind=['StatusIn', 'StatusOut'])
    def Error(self, status_in, status_out):
        return status_in and status_out

    @logical_attribute(
        dtype=bool,
        bind=['StatusIn', 'StatusOut'])
    def Moving(self, status_in, status_out):
        return not status_in and not status_out

    # Proxy commands

    @proxy_command(
        property_name="MoveInAttribute",
        write_attribute=True)
    def MoveIn(self, subcommand):
        subcommand(1)

    @proxy_command(
        property_name="MoveOutAttribute",
        write_attribute=True)
    def MoveOut(self, subcommand):
        subcommand(1)

    # State and status

    @state_attribute(
        bind=['Error', 'StatusIn'])
    def state(self, error, status_in):
        if error:
            return DevState.FAULT, "A conflict has been detected"
        elif moving:
            return DevState.MOVING, "The screen is moving"
        elif status_in:
            return DevState.INSERT, "The screen is inserted"
        else:
            return DevState.EXTRACT, "The screen is exctracted"


if __name__ == '__main__':
    CameraScreen.run_server()
```

Unit testing
------------

Run the tests using:

```console
$ python setup.py test
```


Documentation
-------------

This project has no actual documentation yet.


Contact
-------

Vincent Michel: vincent.michel@maxlab.lu.se
