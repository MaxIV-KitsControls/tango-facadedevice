tango-facadedevice
==================

[![Documentation Status](https://readthedocs.org/projects/tango-facadedevice/badge/?version=latest)](http://tango-facadedevice.readthedocs.io/en/latest/?badge=latest)
[![Build Status](https://travis-ci.org/MaxIV-KitsControls/tango-facadedevice.svg?branch=master)](https://travis-ci.org/MaxIV-KitsControls/tango-facadedevice)
[![Coverage Status](https://coveralls.io/repos/github/MaxIV-KitsControls/tango-facadedevice/badge.svg?branch=master)](https://coveralls.io/github/MaxIV-KitsControls/tango-facadedevice?branch=master)

This python package provide a descriptive interface for reactive high-level
Tango devices.


Requirements
------------

The library requires:

 - python >= 2.7 or >= 3.4
 - pytango >= 9.2.1

Generating the documentation requires:

 - sphinx
 - sphinx.ext.autodoc
 - sphinx.ext.napoleon

The unit-tests require:

 - pytest
 - pytest-runner
 - pytest-mock
 - pytest-xdist
 - pytest-coverage


Documentation
-------------

The documentation is hosted on [ReadTheDocs][1].

Build the documentation using:

```console
$ python setup.py build_sphinx
$ sensible-browser build/sphinx/html/index.html
```


Unit testing
------------

The tests run on [TravisCI][2] and the coverage report is updated on [Coveralls][3]

Run the tests using:

```console
$ python setup.py test
```


Contact
-------

Vincent Michel: vincent.michel@maxlab.lu.se

[1]: http://tango-facadedevice.readthedocs.io/en/latest
[2]: https://travis-ci.org/MaxIV-KitsControls/tango-facadedevice
[3]: https://coveralls.io/github/MaxIV-KitsControls/tango-facadedevice?branch=master
