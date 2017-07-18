#!/usr/bin/env python

# Imports
import sys
from setuptools import setup

# Arguments
TESTING = any(x in sys.argv for x in ['test', 'pytest'])


# README helper
def get_readme(name='README.rst'):
    """Get readme file contents without the badges."""
    with open(name) as f:
        return '\n'.join(
            line for line in f.read().splitlines()
            if not line.startswith('|')
            or not line.endswith('|'))


# Setup
setup(
    name='facadedevice',
    version='1.0.1',
    packages=['facadedevice'],

    # Metadata
    description=(
        "Provide a descriptive interface for "
        "reactive high-level Tango devices."),
    author="Vincent Michel",
    author_email="vincent.michel@esrf.fr",
    license="GPLv3",
    url="https://github.com/MaxIV-KitsControls/tango-facadedevice",
    long_description=get_readme(),

    # Classifiers
    classifiers=[
        'Intended Audience :: Developers',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Topic :: Scientific/Engineering',
        'Topic :: Software Development :: Libraries'],

    # Requirements
    install_requires=['pytango>=9.2.1'],
    tests_require=['pytest-mock', 'pytest-xdist', 'pytest-coverage'],
    setup_requires=['pytest-runner'] if TESTING else [],
)
