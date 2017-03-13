#!/usr/bin/env python

# Imports
import sys
from setuptools import setup

# Arguments
TESTING = any(x in sys.argv for x in ['test', 'pytest'])


# Read function
def safe_read(fname):
    try:
        return open(fname).read()
    except IOError:
        return ""

# Setup
setup(
    name="facadedevice",
    version="0.8.1",
    packages=['facadedevice'],

    # Metadata
    description="Provide a facade device to subclass.",
    author="Vincent Michel",
    author_email="vincent.michel@maxlab.lu.se",
    license="GPLv3",
    url="http://www.maxlab.lu.se",
    long_description=safe_read("README.md"),


    # Requirements
    install_requires=['pytango>=9.2.1'],
    tests_require=['pytest', 'pytest-mock', 'pytest-xdist'],
    setup_requires=['pytest-runner'] if TESTING else [],
)
