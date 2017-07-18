tango-facadedevice
==================

|Doc Status|
|Build Status|
|Coverage Status|

This python package provide a descriptive interface for reactive high-level
Tango devices.


Requirements
------------

The library requires:

- **python** >= 2.7 or >= 3.4
- **pytango** >= 9.2.1


Installation
------------

Install the library by running::


    $ python setup.py install # Or
    $ pip install .


Documentation
-------------

The documentation is hosted on ReadTheDocs_.

Generating the documentation requires:

- sphinx
- sphinx.ext.autodoc
- sphinx.ext.napoleon

Build the documentation using::

    $ python setup.py build_sphinx
    $ sensible-browser build/sphinx/html/index.html


Unit testing
------------

The tests run on TravisCI_ and the coverage report is updated on Coveralls_

Run the tests using::

    $ python setup.py test

The following libraries will be downloaded if necessary:

- pytest
- pytest-runner
- pytest-mock
- pytest-xdist
- pytest-coverage


Contact
-------

Vincent Michel: vincent.michel@esrf.fr

.. |Doc Status| image:: http://readthedocs.org/projects/tango-facadedevice/badge/?version=latest
		:target: http://tango-facadedevice.readthedocs.io/en/latest/?badge=latest
		:alt:

.. |Build Status| image:: https://travis-ci.org/MaxIV-KitsControls/tango-facadedevice.svg?branch=master
                  :target: https://travis-ci.org/MaxIV-KitsControls/tango-facadedevice
                  :alt:

.. |Coverage Status| image:: https://coveralls.io/repos/github/MaxIV-KitsControls/tango-facadedevice/badge.svg?branch=master
                  :target: https://coveralls.io/github/MaxIV-KitsControls/tango-facadedevice?branch=master
                  :alt:

.. _ReadTheDocs: http://tango-facadedevice.readthedocs.io/en/latest
.. _TravisCI: https://travis-ci.org/MaxIV-KitsControls/tango-facadedevice
.. _Coveralls: https://coveralls.io/github/MaxIV-KitsControls/tango-facadedevice?branch=master
