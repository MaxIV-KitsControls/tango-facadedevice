python-facadedevice
===================
***

Provide a facade device to subclass.

Information
-----------

 - Package: python-facadedevice
 - Device:  Facade (+ FacadeMeta)
 - Repo:    [lib-maxiv-facadedevice][repo]

[repo]: https://github.com/MaxIV-KitsControls/lib-maxiv-facadedevice.git


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
        prop="InStatusTag",
        dtype=bool)

    StatusOut = proxy_attribute(
        device="OPCDevice",
        prop="OutStatusTag",
        dtype=bool)

    # Logical attributes
    @logical_attribute(dtype=bool)
    def Error(self, data):
        return data["StatusIn"] == data["StatusOut"]

    # Proxy commands
    MoveIn = proxy_command(
        device="OPCDevice",
        prop="InCmdTag",
        attr=True,
        value=1)

    MoveOut = proxy_command(
        device="OPCDevice",
        prop="OutCmdTag",
        attr=True,
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


Documentation
-------------

This project has no documentation yet, but I'm pasting below some explainantions that should be refactored properly at some point:

A Facade device has its own way of dealing with communication errors: any communication error with the proxies will cause the device to go to fault state, set all the forwarded/logical attributes with an INVALID quality (not the local attributes though), and prevent the execution of forwarded commands. The status should also be pretty explicit. Then the device is frozen and it won't update its state, status or attributes any more.

Now, about recovering. The Facade device do not recover from communication error, unless they come from a change event. That means that if you want your device to reconnect automatically, you need the following configuration:

- in the sub-devices, configure all the attributes to forward to push events (enable polling and set a threshold if necessary)
- make sure everything is accessible when your first start the device (the device do not reconnect if it has never started)
- check the report of the GetInfo command to make sure the facade device used subscription and not polling for all the attributes it forwards.

It turns out there is a way to configure the device to ensure this recovering behavior: you need to set those properties:

- PushEvent: True
- UpdatePeriod: 0

With this configuration, the device will go to FAULT if it is not able to subscribe to all the attributes. That also means there won't be any internal polling and the device will be fully "reactive".


Contact
-------

Vincent Michel: vincent.michel@maxlab.lu.se
