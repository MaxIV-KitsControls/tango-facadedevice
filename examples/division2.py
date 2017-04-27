from facadedevice import Facade, proxy_attribute, logical_attribute


class Division2(Facade):

    A = proxy_attribute(
        dtype=float,
        property_name='AAttribute')

    B = proxy_attribute(
        dtype=float,
        property_name='BAttribute')

    @logical_attribute(
        dtype=float,
        bind=['A', 'B'])
    def C(self, a, b):
        return a / b

if __name__ == '__main__':
    Division2.run_server()
