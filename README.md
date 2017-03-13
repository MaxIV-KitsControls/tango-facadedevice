python-facadedevice
===================
***

Provide a facade devices to subclass.

Information
-----------

 - Package: python-facadedevice
 - Device:  Facade (+ TimedFacade)
 - Repo:    [lib-maxiv-facadedevice][repo]

[repo]: https://github.com/MaxIV-KitsControls/lib-maxiv-facadedevice.git


Usage
-----

The facade devices support the following objects:

- **proxy_attribute**: TANGO attribute linked to the attribute of a remote
  device. Full attribute name is given as property. It supports the
  standard attribute keywords. Optionally, a conversion method can be given.

- **logical_attribute**: TANGO attribute computed from the values of other
  attributes. Use it as a decorator to register the function that make this
  computation.

- **state_attribute**: It is used to describe the logical relationship between
  state/status and the other attributes. It is very similar to logical attributes.

- **combined_attribute**: TANGO attribute computed from the values of other
  remote attributes. Use it as a decorator to register the function that make this
  computation. The remote attribute names are provided by a property, either as a
  list or a pattern.

- **local_attribute**: TANGO attribute holding a local value. Useful for configuring
  the device at runtime.

- **proxy_command**: TANGO command to write an attribute of a remote device
  with a given value. The full attribute name is given as a property. It
  supports standard command keywords.

Moreover, the `Facade` device is fully subclassable in a standard pythonic way
(super, calls to parent methods, etc).

The `TimedFacade` class already implement a `Time` attribute that can be used to
run periodic update (by binding to a logical attribute).


Example
-------

```python
# Example
class CameraScreen(Facade):

    # Proxy attributes

    StatusIn = proxy_attribute(
	    dtype=bool,
        prop="StatusInAttribute")

    StatusOut = proxy_attribute(
        dtype=bool,
        prop="StatusOutAttribute")

    # Logical attributes

    @logical_attribute(
		dtype=bool,
		bind=['StatusIn', 'StatusOut'])
    def Error(self, status_in, status_out):
        return status_in == status_out

    # Proxy commands

    @proxy_command(
        prop="MoveInAttr",
        attr=True)
	def MoveIn(self, subcommand):
		subcommand(1)

    @proxy_command(
        prop="MoveOutAttr",
        attr=True)
	def MoveOut(self, subcommand):
	    subcommand(1)

    # State and status

	@state_attribute
    def state(self, error, status_in):
        if error:
            return DevState.FAULT, "Conflict between IN and OUT"
		if status_in:
            return DevState.INSERT, "IN"
        return DevState.EXTRACT, "OUT"

```

Unit testing
------------

Statement coverage is currently greater than ??%.


Documentation
-------------

This project has no actual documentation yet.


Contact
-------

Vincent Michel: vincent.michel@maxlab.lu.se
