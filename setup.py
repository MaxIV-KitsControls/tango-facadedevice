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
setup(name="facadedevice",
      version="0.6.9",
      description="Provide a facade device to subclass.",
      author="Vincent Michel",
      author_email="vincent.michel@maxlab.lu.se",
      license="GPLv3",
      url="http://www.maxlab.lu.se",
      long_description=safe_read("README.md"),
      packages=['facadedevice'],
      setup_requires=['nose', 'rpm2'],
      install_requires=['PyTango'],
      tests_require=['mock', 'python-devicetest'],
      dependency_links=['git+https://github.com/vxgmichel/pytango-devicetest.git#egg=python-devicetest',
                        'git+https://github.com/vxgmichel/setuptools-rpm2.git#egg=rpm2']
      )
