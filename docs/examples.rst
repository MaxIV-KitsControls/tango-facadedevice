Examples
========

Simple example
--------------

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

Real-world example
------------------

A real-world example of a camera screen device used at MAX-IV:

.. sourcecode:: python

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
