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
