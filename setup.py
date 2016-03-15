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
import shutil
from setuptools import setup, find_packages

sys.path.append(os.path.join(os.path.dirname(__file__), 'uavcan_gui_tool'))
from version import __version__

assert sys.version_info[0] == 3, 'Python 3 is required'

PACKAGE_NAME = 'uavcan_gui_tool'

ICON = os.path.join(PACKAGE_NAME, 'icons', 'logo_256x256.png')

#
# Setup args
#
args = dict(
    name=PACKAGE_NAME,
    version='.'.join(map(str, __version__)),
    packages=find_packages(),
    install_requires=[
        'uavcan',
        'pyserial',
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
            '{0}={0}.main:main'.format(PACKAGE_NAME),
        ]
    },
    data_files=[
        ('', [ICON]),           # This icon will be used by the application itself, not by DE etc.
    ],

    # Meta fields, they have no technical meaning
    description='Cross-platform GUI tool for UAVCAN protocol',
    author='Pavel Kirienko',
    author_email='uavcan@googlegroups.com',
    url='http://uavcan.org',
    license='MIT',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: End Users/Desktop',
        'Intended Audience :: Developers',
        'Topic :: Scientific/Engineering :: Human Machine Interfaces',
        'Topic :: Scientific/Engineering :: Visualization',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3',
    ]
)

#
# Handling additional features for a Freedesktop-compatible OS
#
if 'install_desktop' in sys.argv:
    # Injecting installation dependency ad-hoc
    args.setdefault('setup_requires', []).append('install_freedesktop')

    # Resolving icon installation path (standard for Freedesktop)
    icon_installation_path = os.path.join(sys.prefix, 'share/icons/hicolor/256x256/apps', PACKAGE_NAME + '.png')

    # Writing Desktop entry installation details
    args['desktop_entries'] = {
        PACKAGE_NAME: {
            'Name': 'UAVCAN GUI Tool',
            'GenericName': 'CAN Bus Diagnostics Tool',
            'Categories': 'Development;Utility;',
            'Icon': icon_installation_path,
        }
    }

    # Manually installing the icon (we can't use data_files because... oh, I don't even want to explain that, sorry)
    print('Permanently installing icon to:', icon_installation_path)
    try:
        shutil.rmtree(icon_installation_path)
    except Exception:
        pass
    shutil.copy(ICON, icon_installation_path)


setup(**args)
