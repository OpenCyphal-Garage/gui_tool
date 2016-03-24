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
import glob
import subprocess
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
    setup_requires=[
        'setuptools',
        'setuptools_git>=1.0',
    ],
    install_requires=[
        'setuptools',
        'uavcan>=1.0.0.dev11',
        'pyserial>=2.6',
        'qtawesome>=0.3.1',
        'qtconsole>=4.2.0',
        'numpy',
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
    include_package_data=True,

    # Meta fields, they have no technical meaning
    description='UAVCAN Bus Management and Diagnostics App',
    author='UAVCAN Development Team',
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
if sys.platform.startswith('linux') and ('install' in sys.argv):
    print('Freedesktop components will be installed')

    # Delegating the desktop integration work to 'install_freedesktop'
    args.setdefault('setup_requires', []).append('install_freedesktop')
    if 'install_desktop' not in sys.argv:
        sys.argv.append('install_desktop')

    # Resolving icon installation path (standard for Freedesktop)
    icon_installation_path = os.path.join(sys.prefix, 'share/icons/hicolor/256x256/apps', PACKAGE_NAME + '.png')

    # Writing Desktop entry installation details
    args['desktop_entries'] = {
        PACKAGE_NAME: {
            'Name': HUMAN_FRIENDLY_NAME,
            'GenericName': args['description'],
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
    try:
        os.makedirs(os.path.dirname(icon_installation_path))
    except Exception:
        pass
    shutil.copy(ICON_HIRES, icon_installation_path)

#
# Windows-specific options
#
WINDOWS_SIGNATURE_TIMESTAMPING_SERVER = 'http://timestamp.verisign.com/scripts/timstamp.dll'

def get_windows_signtool_path():
    # TODO: Search for signtool properly
    p = os.path.join(r'C:\Program Files (x86)\Windows Kits\10\bin\x86', 'signtool.exe')
    if os.path.isfile(p):
        return p
    raise RuntimeError('signtool.exe not found')

if os.name == 'nt':
    # Injecting installation dependency ad-hoc
    args.setdefault('setup_requires', []).append('cx_Freeze')

if ('bdist_msi' in sys.argv) or ('build_exe' in sys.argv):
    import cx_Freeze

    # cx_Freeze can't handle 3rd-party packages packed in .egg files, so we have to extract them for it
    dependency_eggs_to_unpack = [
        'uavcan',
        'qtpy',
        'qtconsole',
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
    import qtconsole
    import PyQt5
    import zmq
    import pygments
    import IPython
    import ipykernel
    import jupyter_client
    import traitlets
    import numpy

    # Oh, Windows, never change.
    missing_dlls = glob.glob(os.path.join(os.path.dirname(numpy.core.__file__), '*.dll'))
    print('Missing DLL:', missing_dlls)

    # My reverence for you, I hope, will help control my inborn instability; we are accustomed to a zigzag way of life.
    args['options'] = {
        'build_exe': {
            'packages': [
                'pkg_resources',
                'zmq',
                'pygments',
                'jupyter_client',
            ],
            'include_msvcr': True,
            'include_files': [
                # cx_Freeze doesn't respect the DSDL definition files that are embedded into the package,
                # so we need to include the Pyuavcan package as data in order to work-around this problem.
                # Despite the fact that Pyuavcan is included as data, we still need cx_Freeze to analyze its
                # dependencies, so we don't exclude it explicilty.
                os.path.join(unpacked_eggs_dir, 'uavcan'),
                # Same thing goes with the main package - we want its directory structure untouched, so we include
                # it as data, too.
                PACKAGE_NAME,
                # These packages don't work properly when packed in .zip, so here we have another bunch of ugly hacks
                os.path.join(unpacked_eggs_dir, os.path.dirname(PyQt5.__file__)),
                os.path.join(unpacked_eggs_dir, os.path.dirname(qtawesome.__file__)),
                os.path.join(unpacked_eggs_dir, os.path.dirname(qtconsole.__file__)),
                os.path.join(unpacked_eggs_dir, os.path.dirname(zmq.__file__)),
                os.path.join(unpacked_eggs_dir, os.path.dirname(pygments.__file__)),
                os.path.join(unpacked_eggs_dir, os.path.dirname(IPython.__file__)),
                os.path.join(unpacked_eggs_dir, os.path.dirname(ipykernel.__file__)),
                os.path.join(unpacked_eggs_dir, os.path.dirname(jupyter_client.__file__)),
                os.path.join(unpacked_eggs_dir, os.path.dirname(traitlets.__file__)),
                os.path.join(unpacked_eggs_dir, os.path.dirname(numpy.__file__)),
            ] + missing_dlls,
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
    def setup(*args, **kwargs):
        # Checking preconditions and such
        signtool_path = get_windows_signtool_path()
        print('Using this signtool:', signtool_path)

        pfx_path = glob.glob(os.path.join('..', '*.pfx'))
        if len(pfx_path) != 1:
            raise RuntimeError('Expected to find exactly one PFX in the outer dir, found this: %r' % pfx_path)
        pfx_path = pfx_path[0]
        print('Using this certificate:', pfx_path)

        pfx_password = input('Enter password to read the certificate file: ').strip()

        # Freezing
        cx_Freeze.setup(*args, **kwargs)

        # Code signing the outputs
        print('Signing the outputs...')
        for out in glob.glob(os.path.join('dist', '*.msi')):
            out_copy = '.signed.'.join(out.rsplit('.', 1))
            try:
                shutil.rmtree(out_copy)
            except Exception:
                pass
            shutil.copy(out, out_copy)
            print('Signing file:', out_copy)
            while True:
                try:
                    subprocess.check_call([signtool_path, 'sign',
                                           '/f', pfx_path,
                                           '/p', pfx_password,
                                           '/t', WINDOWS_SIGNATURE_TIMESTAMPING_SERVER,
                                           out_copy])
                except Exception as ex:
                    print('SignTool failed:', ex)
                    if input('Try again? y/[n] ').lower().strip()[0] == 'y':
                        pass
                    else:
                        raise
                else:
                    break
        print('All files were signed successfully')

setup(**args)
