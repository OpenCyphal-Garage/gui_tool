#!/usr/bin/env python3
#
# Copyright (C) 2016  UAVCAN Development Team  <uavcan.org>
#
# This software is distributed under the terms of the MIT License.
#
# Author: Pavel Kirienko <pavel.kirienko@zubax.com>
#

import os
import sys
from setuptools import setup, find_packages

sys.path.append(os.path.join(os.path.dirname(__file__), 'uavcan_gui_tool'))
from version import __version__

assert sys.version_info[0] == 3, 'Python 3 is required'

# Not sure yet if this is a good idea
os.system('git submodule update --init --recursive')

version = '.'.join(map(str, __version__))
print('Version:', version)

# TODO: Migrate to PyQtGraph from PIP when it's updated there. Current version from PIP doesn't work with PyQt5.
packages = find_packages('uavcan_gui_tool') + find_packages('pyqtgraph', exclude=['*examples*'])
print('Packages:', *packages, sep='\n')

dependencies = [
    'uavcan',
    'qtconsole',
    'numpy',
    'matplotlib',
    'pylab',
]

args = dict(
    name='uavcan_gui_tool',
    version=version,
    packages=packages,
    install_requires=dependencies,
    scripts=['bin/uavcan_gui_tool'],

    # Meta fields, they have no technical meaning
    description='Cross-platform GUI tool for UAVCAN protocol',
    author='Pavel Kirienko',
    author_email='uavcan@googlegroups.com',
    url='http://uavcan.org',
    license='MIT',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'Topic :: Scientific/Engineering',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3',
    ]
)

setup(**args)
