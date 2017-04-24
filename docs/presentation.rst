Presentation
============

This python package provide a descriptive interface for reactive high-level
Tango devices.


Requirements
------------

The library requires:

 - python >= 2.7 or >= 3.4
 - pytango >= 9.2.1


Example
-------

The following example shows the definition of a rectangle device,
getting its width and height from other devices:

.. sourcecode:: python

  from facadevice import Facade, proxy_attribute, logical_attribute

  class Rectangle(Facade):

      Width = proxy_attribute(
	  property_name='WidthAttribute')

      Height = proxy_attribute(
	  property_name='HeightAttribute')

      @logical_attribute(
	  bind=['Width', 'Height'])
      def Area(width, height):
          return width * height

   if __name__ == '__main__':
      Rectangle.run_server()

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
