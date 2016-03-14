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

args = dict(
    name='uavcan_gui_tool',
    version='.'.join(map(str, __version__)),
    packages=find_packages(),
    install_requires=[
        'uavcan',
        'qtconsole',
        'numpy',
        'matplotlib',
        'pyqtgraph>=0.9.10',
    ],
    dependency_links=[
        # TODO: Migrate to PyQtGraph from PIP when it's updated there. Current version from PIP doesn't work with PyQt5.
        'https://github.com/pyqtgraph/pyqtgraph/tarball/9d64b269d57c84faa00ecd92474ca67eb45e6094#egg=pyqtgraph-0.9.10',
    ],
    # We can't use "scripts" here, because generated shims don't work with multiprocessing pickler.
    entry_points={
        'gui_scripts': [
            'uavcan_gui_tool = uavcan_gui_tool.main:main',
        ]
    },

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
