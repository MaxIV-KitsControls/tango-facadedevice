Presentation
============

This python package provide a descriptive interface for reactive high-level
Tango devices.


Requirements
------------

The library requires:

 - **python** >= 2.7 or >= 3.4
 - **pytango** >= 9.2.1


Tutorial
--------

Creating an running a facade device
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
A facade device is an enhanced pytango HLAPI device. It provides the same
methods and supports the same pytango object (device properties, attributes,
commands, etc.). In order to create a new facade device class, simply inherit
from the `Facade` base class:

.. literalinclude:: ../examples/empty.py

This example is already a working (empty) device. It is possible to run it
without a database using the `tango.test_context` module:

.. sourcecode:: console

  $ cd examples/
  $ python -m tango.test_context examples.empty.Empty --debug=3
  Ready to accept request
  Empty started on port 8888 with properties {}
  Device access: tango://hostname:8888/test/nodb/empty#dbase=no
  Server access: tango://hostname:8888/dserver/Empty/empty#dbase=no

It is now accessible through `itango`::

  In [1]: d = Device('tango://hostname:8888/test/nodb/empty#dbase=no')
  In [2]: d.state()
  Out[2]: tango._tango.DevState.UNKNOWN

Overriding `safe_init_device`:
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The default state is **UNKNOWN**. Since facade devices are regular devices,
we can change it using the `set_state` method. However, the `init_device` method
shouldn't be overridden because it performs specific exception handling. Instead,
override `safe_init_device` if you have to add some extra logic. Don't forget to
call the parent method since it performs other useful steps:

.. literalinclude:: ../examples/on.py
   :pyobject: On

Now let's check the state::

  In [2]: d.state()
  Out[2]: tango._tango.DevState.ON

Local attributes
^^^^^^^^^^^^^^^^

Good, but a static state is not really useful. Instead we'd like it to react to
the values of other attributes. Let's create a device with a local counter using
the `local_attribute` object.

.. literalinclude:: ../examples/counter1.py
   :pyobject: Counter1

Note that `local_attribute` can be used as a decorator to set a default value
for the attribute, although it is not mandatory. Also, `local_attribute` (and
other facade-specific attributes) supports all the arguments of the standard
pytango attribute object (e.g. `access` and `dtype` in the example above). Now
let's try our counter::

  In [2]: d.count
  Out[2]: 0
  In [3]: d.count += 1
  In [4]: d.count
  Out[4]: 1

See how the `count` attribute has been incremented successfully. Also note that
the facade devices have a full support for events, meaning a change event has
been pushed when the `count` value has been updated (no polling is required on
the attribute).

Data model
^^^^^^^^^^

Now, instead of a writable attribute, we'd like to use a command to increment
the value of `count`. But first, we need to learn about the data model that
allows reactivity and the propagation of changes. Every facade device instance
has a graph of nodes that represents the different values that the device has
to manage. For instance, every local attribute has a corresponding node that
can be accessed through `self.graph[attr_name]`. A node can contain either:

- nothing
- a triplet result (value, stamp, quality)
- an exception

Accessing the node state is done through the following methods:

- `node.result() == None` if the node contains nothing
- `value, stamp, quality = node.result()` if the node contains a result
- `node.exception() == None` if the node doesn't contain an exception
- `exc = node.exception()` if the node contains an exception

Also note that calling `node.result()` on a node containing an exception
will raise the corresponding exception. The node state is set using the
following methods:

- `node.set_result(None)`
- `node.set_result((value, stamp, quality))`
- `node.set_exception(exc)`

Note that stamp and quality are optional. They respectively default to the
current time and the **VALID** quality. The `increment` tango command can
now be implemented:

.. literalinclude:: ../examples/counter2.py
   :pyobject: Counter2

Let's give it a try::

  In [2]: d.count
  Out[2]: 0
  In [3]: d.increment()
  In [4]: d.count
  Out[4]: 1


State attribute
^^^^^^^^^^^^^^^

Now, we'd like to have the state react to the value of `count`. This can be
achieved using the `state_attribute` facade object. It is used as a decorator
and takes the list of the nodes to bind to as an argument:

.. literalinclude:: ../examples/counter3.py
   :pyobject: Counter3

Note that it's possible to return the status along with the state, although it
is not mandatory. Let's run the counter::

  In [19]: d.state()
  Out[19]: tango._tango.DevState.OFF
  In [20]: d.status()
  Out[20]: 'The count is 0'
  In [21]: d.increment()
  In [22]: d.state()
  Out[22]: tango._tango.DevState.ON
  In [23]: d.status()
  Out[23]: 'The count is 1'

See how the state is updated automatically. Remember that there is no polling
or periodic update involved: the changes are simply propagated through the
device graph.
