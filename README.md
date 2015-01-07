tangods-facadedevice
===================
***

Provide a facade device to subclass.

Information
-----------

 - Package: tangods-facadedevice
 - Device:  Facade (+ FacadeMeta)
 - Repo:    [dev-maxiv-facadedevice][repo]

[repo]: https://gitorious.maxlab.lu.se/kits-maxiv/dev-maxiv-facadedevice/


Usage
-----

In order to subclass the `Facade` device, it is required to define `FacadeMeta`
as metaclass. The proxy device supports the following objects:

- **proxy_attribute**: TANGO attribute linked to the attribute of a remote
  device. Attribute and device are given as property names. It supports the
  standard attribute keywords.

- **logical_attribute**: TANGO attribute computed from the values of other
  attributes. Use it as a decorator to register the function that make this
  computation. The decorated method takes the attribute value dictionnary as
  argument. Logical attributes also support the standard attribute keywords.

- **proxy_command**: TANGO command to write an attribute of a remote device
  with a given value. Attribute and device are given as property names. It
  supports standard command keywords.

In order to define the state and status of the device, these two methods can be
overriden:

- **state_from _data**: return the state to set, or None
- **status_from _data**: return the status to set, or None

Moreover, the `Facade` device is fully subclassable in a standard pythonic way
(super, calls to parent methods, etc).

Example
-------

```python
# Example
class CameraScreen(Facade):
    __metaclass__ = FacadeMeta

    # Proxy attributes
    StatusIn = proxy_attribute(
        device="OPCDevice",
        attr="InStatusTag",
        dtype=bool)

    StatusOut = proxy_attribute(
        device="OPCDevice",
        attr="OutStatusTag",
        dtype=bool)

    # Logical attributes
    @logical_attribute(dtype=bool)
    def Error(self, data):
        return data["StatusIn"] == data["StatusOut"]

    # Proxy commands
    MoveIn = proxy_command(
        device="OPCDevice",
        attr="InCmdTag",
        value=1)

    MoveOut = proxy_command(
        device="OPCDevice",
        attr="OutCmdTag",
        value=1)

    # State
    def state_from_data(self, data):
        if data['Error']:
            return DevState.FAULT
        return DevState.INSERT if data['StatusIn'] else DevState.EXTRACT

    # Status
    def status_from_data(self, data):
        if data['Error']:
            return "Conflict between IN and OUT informations"
        return "IN" if data['StatusIn'] else "OUT"
```

Unit testing
------------

The package is unittested using `devicetest` and the example class given above.

Statement coverage is currently greater than 84%.

Contact
-------

Vincent Michel: vincent.michel@maxlab.lu.se
