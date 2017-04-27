Presentation
============

This python package provide a descriptive interface for reactive high-level
Tango devices.


Requirements
------------

The library requires:

 - python >= 2.7 or >= 3.4
 - pytango >= 9.2.1


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
