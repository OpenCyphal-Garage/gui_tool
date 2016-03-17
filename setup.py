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
import pkg_resources
from setuptools import setup, find_packages
from setuptools.archive_util import unpack_archive

PACKAGE_NAME = 'uavcan_gui_tool'
HUMAN_FRIENDLY_NAME = 'UAVCAN GUI Tool'

sys.path.append(os.path.join(os.path.dirname(__file__), PACKAGE_NAME))
from version import __version__

assert sys.version_info[0] == 3, 'Python 3 is required'

ICON_HIRES = os.path.join(PACKAGE_NAME, 'icons', 'logo_256x256.png')
ICON_ICO = os.path.join(PACKAGE_NAME, 'icons', 'logo.ico')

#
# Setup args common for all targets
#
args = dict(
    name=PACKAGE_NAME,
    version='.'.join(map(str, __version__)),
    packages=find_packages(),
    install_requires=[
        'uavcan',
        'pyserial',
        'qtawesome',
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
        ('', [ICON_HIRES]),           # This icon will be used by the application itself, not by DE etc.
    ],

    # Meta fields, they have no technical meaning
    description='UAVCAN bus management and diagnostics app',
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
        'Environment :: X11 Applications',
        'Environment :: Win32 (MS Windows)',
        'Environment :: MacOS X',
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
            'Name': HUMAN_FRIENDLY_NAME,
            'GenericName': 'CAN Bus Diagnostics Tool',
            'Comment': args['description'],
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

#
# Windows-specific options
#
if os.name == 'nt':
    # Injecting installation dependency ad-hoc
    args.setdefault('setup_requires', []).append('cx_Freeze')

if ('bdist_msi' in sys.argv) or ('build_exe' in sys.argv):
    import cx_Freeze

    # cx_Freeze can't handle 3rd-party packages packed in .egg files, so we have to extract them for it
    dependency_eggs_to_unpack = [
        'uavcan',
    ]
    unpacked_eggs_dir = os.path.join('build', 'hatched_eggs')
    sys.path.insert(0, unpacked_eggs_dir)
    try:
        shutil.rmtree(unpacked_eggs_dir)
    except Exception:
        pass
    for dep in dependency_eggs_to_unpack:
        for egg in pkg_resources.require(dep):
            if not os.path.isdir(egg.location):
                unpack_archive(egg.location, unpacked_eggs_dir)

    import qtawesome

    # My reverence for you, I hope, will help control my inborn instability; we are accustomed to a zigzag way of life.
    args['options'] = {
        'build_exe': {
            'include_msvcr': True,
            'include_files': [
                # cx_Freeze doesn't respect the DSDL definition files that are embedded into the package,
                # so we need to include the Pyuavcan package as data in order to work-around this problem.
                # Despite the fact that Pyuavcan is included as data, we still need cx_Freeze to analyze its
                # dependencies, so we don't exclude it explicilty.
                os.path.join(unpacked_eggs_dir, 'uavcan'),
                # QtAwesome needs its data files as well.
                os.path.join(unpacked_eggs_dir, os.path.dirname(qtawesome.__file__)),
                # Same thing goes with the main package - we want its directory structure untouched, so we include
                # it as data, too.
                PACKAGE_NAME,
            ],
        },
        'bdist_msi': {
            'initial_target_dir': '[ProgramFilesFolder]\\UAVCAN\\' + HUMAN_FRIENDLY_NAME,
        },
    }
    args['executables'] = [
        cx_Freeze.Executable(os.path.join('bin', PACKAGE_NAME),
                             base='Win32GUI',
                             icon=ICON_ICO,
                             shortcutName=HUMAN_FRIENDLY_NAME,
                             shortcutDir='ProgramMenuFolder'),
    ]
    # Dispatching to cx_Freeze only if MSI build was requested explicitly. Otherwise continue with regular setup.
    # This is done in order to be able to install dependencies with regular setuptools.
    # TODO: This is probably not right.
    setup = cx_Freeze.setup


setup(**args)
