#!/usr/bin/env python

# Imports
import os
from setuptools import setup


# Read function
def safe_read(fname):
    try:
        return open(os.path.join(os.path.dirname(__file__), fname)).read()
    except IOError:
        return ""

# Setup
setup(name="tangods-facadedevice",
      version="0.2.3",
      description="Provide a facade device to subclass.",
      author="Vincent Michel",
      author_email="vincent.michel@maxlab.lu.se",
      license="GPLv3",
      url="http://www.maxlab.lu.se",
      long_description=safe_read("README.md"),
      packages=['facadedevice'],
      test_suite="nose.collector",
      )
