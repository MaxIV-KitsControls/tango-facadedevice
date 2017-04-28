Examples
========

This section contains a few extra examples.

Simple example
--------------

The following example shows the definition of a rectangle device,
getting its width and height from other devices:

.. literalinclude:: ../examples/rectangle.py

A rectangle device is configured using 2 device properties, e.g.:

  - WidthAttribute: `geometry/point/a/x`
  - HeightAttribute: `geometry/point/b/y`

The remote attributes are expected to push either change or periodic events.

A rectangle device exposes 3 float attributes:

  - Width
  - Height
  - Area

Those attributes will be updated as soon as a corresponding event is received.
They also pushes events, allowing other high-level devices to react to their changes.

Real-world example
------------------

A real-world example of a camera screen device used at MAX-IV:

.. literalinclude:: ../examples/screen.py
