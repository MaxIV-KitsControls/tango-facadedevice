Tutorial
========

This tutorial goes through most of the library features by presenting several
facade devices with increasing complexity.

Creating an running a facade device
-----------------------------------

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


Adding extra logic at initialization
------------------------------------

The default state is **UNKNOWN**. Since facade devices are regular devices,
we can change it using the `set_state` method. However, the `init_device`
method shouldn't be overridden because it performs specific exception handling.
Instead, override `safe_init_device` if you have to add some extra logic. Don't
forget to call the parent method since it performs other useful steps:

.. literalinclude:: ../examples/on.py
   :pyobject: On

Now let's check the state::

  In [2]: d.state()
  Out[2]: tango._tango.DevState.ON


Local attributes
----------------

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
----------

Now, instead of a writable attribute, we'd like to use a command to increment
the value of `count`. But first, we need to learn about the data model that
allows reactivity and the propagation of changes. Every facade device instance
has a graph of nodes that represents the different values that the device has
to manage. For instance, every local attribute has a corresponding node that
can be accessed through `self.graph[attr_name]`. A node can contain either:

- nothing
- a `triplet` result (value, stamp, quality)
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
- `node.set_result(triplet(value, stamp, quality))`
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
---------------

Now, we'd like to have the state react to the value of `count`. This can be
achieved using the `state_attribute` facade object. It is used as a decorator
and takes the list of the nodes to bind to as an argument:

.. literalinclude:: ../examples/counter3.py
   :pyobject: Counter3

Note that it's possible to return the status along with the state, although it
is not mandatory. Let's run the counter::

  In [2]: d.state()
  Out[2]: tango._tango.DevState.OFF
  In [3]: d.status()
  Out[3]: 'The count is 0'
  In [4]: d.increment()
  In [5]: d.state()
  Out[5]: tango._tango.DevState.ON
  In [6]: d.status()
  Out[6]: 'The count is 1'

See how the state is updated automatically. Remember that there is no polling
or periodic update involved: the changes are simply propagated through the
device graph.


Logical attributes
------------------

`State` and `Status` are not the only attributes that can react to changes.
It is possible to declare logical attributes using the same binding approach.
Let's write a device that performs a division:

.. literalinclude:: ../examples/division1.py
   :pyobject: Division1

Here we defined the relationship `C = A / B`. Note how the arguments of the
method `C` are simply the value `A` and `B`. Let's give it a try::

  In [2]: d.A = 1
  In [3]: d.B = 4
  In [4]: d.C
  Out[4]: 0.25
  In [5]: d.B = 0
  In [6]: d.C
  PyDs_PythonError: Exception while updating node <C>:
    float division by zero

Remember that the computation of `C` does not happen when the attribute `C` is
being read but when the values of `A` and `B` are changing. For instance, the
zero division exception has been set to the node `C` right after we set `B` to
zero.

They are special rules about aggregation depending on the state of the
different input nodes:

- if node `A` or node `B` is empty, node `C` is empty too
- if node `A` or node `B` contains an exception, it's propagated to `C`
- if the quality of `A` or the quality of `B` is invalid, the quality of `C`
  is invalid
- otherwise, the `C` method is executed and the return value is used as a
  result

Note that the return value of the `C` method can be:

- a single value (timestamp and quality are computed from the input nodes)
- a `triplet` result, in order to set the timestamp and/or the quality


The triplet structure
---------------------

The triplet is a named tuple provided by the facade device. All the node
results are guaranteed to be a triplet when they exist. This is how it is
used::

  from time import time
  from tango import AttrQuality
  from facadedevice import triplet

  # A triplet from a single value
  result = triplet(1.)

  # A triplet from a value and a stamp
  result = triplet(1., stamp=time())

  # A triplet from a value and a quality
  result = triplet(1, quality=AttrQuality.ALARM)

  # A triplet from value, a stamp and a quality
  result = triplet(1, time(), AttrQuality.CHANGING)

  # Triplets can be unpacked
  value, stamp, quality = result

  # The values can be accessed through attributes
  result.value, result.stamp, result.quality


The default quality is **VALID** and the default stamp is the time at the
triplet creation. It has another interesting property: a `None` value will
cause the quality to be **INVALID** and an **INVALID** quality will cause
the value to be `None`. This is enforced at triplet creation.

.. warning::
   An empty node and a none (invalid) triplet can easily be confused! They
   are however very different:

   - `node.set_result(None)` empty the node
   - `node.set_result(triplet(None))` set an **INVALID** result with a
     timestamp

   The both behave differently when reading the corresponding attribute or
   when used as an input node to propagate changes.


Proxy attribute
---------------

The division device is working nicely but it doesn't really communicate with
the outside world. More precisely, the `A` and `B` might come from another
device. In this case, we can simply replace the local attributes with proxy
attributes:

.. literalinclude:: ../examples/division2.py
   :pyobject: Division2

The only special argument we need to provide a proxy attribute with is
`property_name`: its the name of the device property that will contain
the access to the remote attribute. In this case, the device properties
could be:

  - `AAttribute`: some/device/somewhere/x
  - `BAttribute`: some/other/device/y


Those remote attributes are expected to push either change or periodic events.
Facade devices have an expert command called `GetInfo` that provides extra
information about the event subscription, e.g::

  In [2]: print(d.getinfo())
  The device is currently connected.
  It subscribed to event channel of the following attribute(s):
  - some/device/somewhere/x (CHANGE_EVENT)
  - some/other/device/y (PERIODIC_EVENT)
  -----
  No errors in history since Tue Apr 25 18:26:47 2017 (last initialization).

Once properly set up, any event comming from those remote attributes will
cause `A` (or `B`) and `C` to be updated. Note that facade devices can easily
be chained together since they both publish and subscribe.

It is also possible to apply a conversion to the input data by using
`proxy_attribute` as a decorator::

  @proxy_attribute(
      dtype=float,
      property_name='AAttribute')
  def A(self, a):
      return a * 10

Here, the data coming from the event channel is multiplied by 10. Note that
the device property can also be a value if the remote attribute doesn't
exist:

.. sourcecode:: console

  $ python -m tango.test_context --prop "{'AAttribute': 1.0, 'BAttribute': 4.0}" \
    division2.Division2
  Ready to accept request
  Division2 started on port 8888 with properties {'AAttribute': 1.0, 'BAttribute': 4.0}
  Device access: tango://vinmic-t440p:8888/test/nodb/division2#dbase=no
  Server access: tango://vinmic-t440p:8888/dserver/Division2/division2#dbase=no

Let's check the values::

  In [2]: d.A = 1
  In [3]: d.B = 4
  In [4]: d.C
  Out[4]: 0.25


Combined attributes
-------------------

In some cases, it is interesting to access remote attributes in a more dynamic
way. The `facadedevice` library does not support dymanic attributes directly,
but it provides a `combined_attributes` object that can be used for similar
purposes. Let's say we'd like to compute the average of the values of an
arbitrary list of attributes:

.. literalinclude:: ../examples/average.py
   :pyobject: Average

Here, the `AttributesToAverage` device property is simply the list of all the
attributes that should be used for the computation. The attributes may come
from the same device, or different devices. If that device property is a single
line, it's used a pattern for listing the attributes. For instance, the pattern
`a/b/*/x[12]` might yield:

- a/b/c/x1
- a/b/c/x2
- a/b/whatever/x1
- a/b/whatever/x2
- etc.


It includes all the attributes called `x1` or `x2` from any device starting
with `a/b/`. Note that the aggregation works the same as for logical
attributes.


Proxy commands
--------------

# TODO
