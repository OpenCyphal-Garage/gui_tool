UAVCAN GUI Tool
===============

[![Travis CI](https://travis-ci.org/UAVCAN/gui_tool.svg?branch=master)](https://travis-ci.org/UAVCAN/gui_tool)
[![PyPi](https://img.shields.io/pypi/dm/uavcan_gui_tool.svg)](https://pypi.python.org/pypi/uavcan_gui_tool)
[![Gitter](https://img.shields.io/badge/gitter-join%20chat-green.svg)](https://gitter.im/UAVCAN/general)

UAVCAN GUI Tool is a cross-platform (Windows/Linux/OSX) application for UAVCAN bus management and diagnostics.

![UAVCAN GUI Tool screenshot](screenshot.png "UAVCAN GUI Tool screenshot")

## Installing on Linux

The general approach is simple:

1. Install PyQt5 for Python 3 using your OS' package manager (e.g. APT).
2. Install the application itself from PyPI: `pip3 install uavcan_gui_tool`
(it is not necessary to clone this repository).
Alternatively, if you're a developer and you want to install your local copy, use `pip3 install .`.

It also may be necessary to install additional dependencies, depending on your distribution (see details below).

Once the application is installed, you should see new desktop entries available in your desktop menu;
also a new executable `uavcan_gui_tool` will be available in your `PATH`.
If your desktop environment doesn't update the menu automatically, you may want to do it manually, e.g.
by invoking `sudo update-desktop-database` (command depends on the distribution).

It is also recommended to install Matplotlib - it is not used by the application itself,
but it may come in handy when using the embedded IPython console.

### Debian-based distributions

```bash
sudo apt-get install -y python3-pip python3-numpy python3-pyqt5 python3-pyqt5.qtsvg
sudo pip3 install uavcan_gui_tool
```

#### Troubleshooting

If installation fails with an error like below, try to install IPython directly with `sudo pip3 install ipython`:

> error: Setup script exited with error in ipython setup command:
> Invalid environment marker: sys_platform == "darwin" and platform_python_implementation == "CPython"

If you're still unable to install the package, please open a ticket.

### RPM-based distributions

*Maintainers wanted*

## Installing on Windows

In order to install this application,
**download and install the latest `.msi` package from here: <https://files.zubax.com/products/org.uavcan.gui_tool/>**.

### Building the MSI package

These instructions are for developers only. End users should use pre-built MSI packages (see the link above).

First, install dependencies:

* [WinPython 3.4 or newer, pre-packaged with PyQt5](http://winpython.github.io/).
Make sure that `python` can be invoked from the terminal; if it can't, check your `PATH`.
* Windows 10 SDK.
[Free edition of Visual Studio is packaged with Windows SDK](https://www.visualstudio.com/).

Then, place the `*.pfx` file containing the code signing certificate in the outer directory
(the build script will search for `../*.pfx`).
Having done that, execute the following (the script will prompt you for password to read the certificate file):

```dos
python setup.py install
python setup.py bdist_msi
```

Collect the resulting signed MSI from `dist/`.

## Installing on OSX

***MAINTAINERS WANTED***

## Development

### Releasing new version

First, deploy the new version to PyPI. In order to do that, perform the following steps:

1. Update the version tuple in `version.py`, e.g. `1, 0`, and commit this change.
2. Create a new tag with the same version number as in the version file, e.g. `git tag -a 1.0 -m v1.0`.
3. Push to master: `git push && git push --tags`

Then, build a Windows MSI package using the instructions above, and upload the resulting MSI to
the distribution server.

### Code style

The code should be formatted in compliance with [PEP8](https://www.python.org/dev/peps/pep-0008/),
with one exception: line length must not exceed 120 characters (PEP8 requires 79).
