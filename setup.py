#!/usr/bin/env python
from setuptools import setup

# Setup
setup(
    name="facadedevice",
    packages=["facadedevice"],
    # SCM versioning
    use_scm_version=True,
    setup_requires=["setuptools_scm"],
    # Metadata
    description=(
        "Provide a descriptive interface for "
        "reactive high-level Tango devices."
    ),
    author="Vincent Michel",
    author_email="vincent.michel@esrf.fr",
    license="GPLv3",
    url=(
        "https://gitlab.maxiv.lu.se/"
        "kits-maxiv/plc2tango/lib-maxiv-facadedevice"
    ),
    # Classifiers
    classifiers=[
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Topic :: Scientific/Engineering",
        "Topic :: Software Development :: Libraries",
    ],
    # Requirements
    install_requires=["pytango>=9.2.1", "numpy"],
)
