UAVCAN GUI Tool
===============

[![Gitter](https://img.shields.io/badge/gitter-join%20chat-green.svg)](https://gitter.im/UAVCAN/general)

UAVCAN GUI Tool is a cross-platform (Windows/Linux/OSX) application for UAVCAN bus management and diagnostics.

![UAVCAN GUI Tool screenshot](screenshot.png "UAVCAN GUI Tool screenshot")

## Installing on Linux

The general approach is simple:

1. Install PyQt5 for Python 3 using your OS' package manager (e.g. APT). Make sure that PyQt4 is not installed for Python 3.
2. Install the application itself via `./setup.py install`.

It also may be necessary to install additional dependencies, depending on your distribution (see details below).

Once the application is installed, you should see the new desktop entries available in your desktop menu;
also a new executable `uavcan_gui_tool` will be available in your `PATH`.
If your desktop environment doesn't update the menu automatically, you may want to do it manually, e.g.
by invoking `sudo update-desktop-database` (command depends on the distribution).

It is also recommended to install Matplotlib - it is not used by the application itself,
but it may come in handy when using the embedded IPython console.

### Debian-based distributions

```bash
sudo apt-get update; sudo apt-get upgrade -y
sudo apt-get install -y python3-numpy python3-pyqt5 python3-pyqt5.qtsvg
sudo ./setup.py install
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

First, install [WinPython 3.4 or newer, pre-packaged with PyQt5](http://winpython.github.io/).
Make sure that `python` can be invoked from the terminal; if it can't, check your `PATH`.
Having done that, execute the following:

```dos
python setup.py install
python setup.py bdist_msi
```

Collect the resulting MSI from `dist/`.

## Installing on OSX

***MAINTAINERS WANTED***
