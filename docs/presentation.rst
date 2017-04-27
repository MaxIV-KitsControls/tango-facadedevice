Presentation
============

This python package provide a descriptive interface for reactive high-level
Tango devices.


Requirements
------------

The library requires:

 - **python** >= 2.7 or >= 3.4
 - **pytango** >= 9.2.1


Installation
------------

Install the library by running:

.. sourcecode:: console

  $ python setup.py install # Or
  $ pip install .


Unit-testing
------------

Run the tests using:

.. sourcecode:: console

  $ python setup.py test

The following libraries will be downloaded if necessary:

- pytest
- pytest-runner
- pytest-mock
- pytest-xdist
- pytest-coverage


Documentation
-------------

Generating the documentation requires:

- sphinx
- sphinx.ext.autodoc
- sphinx.ext.napoleon

Build the documentation using:

.. sourcecode:: console

  $ python setup.py build_sphinx
  $ sensible-browser build/sphinx/html/index.html
