#
# Copyright (C) 2016  UAVCAN Development Team  <uavcan.org>
#
# This software is distributed under the terms of the MIT License.
#
# Author: Pavel Kirienko <pavel.kirienko@zubax.com>
#

import sys
import glob
from widgets import show_error, get_monospace_font
from PyQt5.QtWidgets import QDialog, QSpinBox, QComboBox, QLineEdit, QPushButton, QLabel, QVBoxLayout, QCompleter
from PyQt5.QtCore import Qt
from logging import getLogger
from collections import OrderedDict


logger = getLogger(__name__)


def _linux_parse_proc_net_dev(out_ifaces):
    with open('/proc/net/dev') as f:
        for line in f:
            if ':' in line:
                name = line.split(':')[0].strip()
                out_ifaces.insert(0 if 'can' in name else len(out_ifaces), name)
    return out_ifaces


def _linux_parse_ip_link_show(out_ifaces):
    import re
    import subprocess
    import tempfile

    with tempfile.TemporaryFile() as f:
        proc = subprocess.Popen('ip link show', shell=True, stdout=f)
        if 0 != proc.wait(10):
            raise RuntimeError('Process failed')
        f.seek(0)
        out = f.read().decode()

    return re.findall(r'\d+?: ([a-z0-9]+?):\ <[^>]*UP[^>]*>.*\n *link/can', out) + out_ifaces


def list_ifaces():
    """Returns dictionary, where key is description, value is the OS assigned name of the port"""
    if 'linux' in sys.platform.lower():
        # Linux system
        ifaces = glob.glob('/dev/serial/by-id/*')
        # noinspection PyBroadException
        try:
            ifaces = _linux_parse_ip_link_show(ifaces)       # Primary
        except Exception as ex:
            logger.warning('Could not parse "ip link show": %s', ex, exc_info=True)
            ifaces = _linux_parse_proc_net_dev(ifaces)       # Fallback

        out = OrderedDict()
        for x in ifaces:
            out[x] = x

        return out
    else:
        # Windows, Mac, whatever
        import serial.tools.list_ports

        out = OrderedDict()
        for port, name, _ in serial.tools.list_ports.comports():
            out[name] = port

        return out


def run_iface_config_window(icon):
    ifaces = list_ifaces()

    win = QDialog()
    win.setWindowTitle('CAN Interface Configuration')
    win.setWindowIcon(icon)
    win.setWindowFlags(Qt.CustomizeWindowHint | Qt.WindowTitleHint | Qt.WindowCloseButtonHint)

    combo = QComboBox(win)
    combo.setEditable(True)
    combo.setInsertPolicy(QComboBox.NoInsert)
    combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
    combo.addItems(ifaces.keys())

    combo_completer = QCompleter()
    combo_completer.setCaseSensitivity(Qt.CaseSensitive)
    combo_completer.setModel(combo.model())
    combo.setCompleter(combo_completer)

    bitrate = QSpinBox()
    bitrate.setMaximum(1000000)
    bitrate.setMinimum(10000)
    bitrate.setValue(1000000)

    extra_args = QLineEdit()
    extra_args.setFont(get_monospace_font())

    ok = QPushButton('OK', win)

    result = None
    kwargs = {}

    def on_ok():
        nonlocal result, kwargs
        a = str(extra_args.text())
        if a:
            try:
                kwargs = dict(eval(a))
            except Exception as ex:
                show_error('Invalid parameters', 'Could not parse optional arguments', ex, parent=win)
                return
        kwargs['bitrate'] = int(bitrate.value())
        result_key = str(combo.currentText()).strip()
        try:
            result = ifaces[result_key]
        except KeyError:
            result = result_key
        win.close()

    ok.clicked.connect(on_ok)

    layout = QVBoxLayout()
    layout.addWidget(QLabel('Select CAN interface or serial port for SLCAN:'))
    layout.addWidget(combo)
    layout.addWidget(QLabel('Interface bitrate (SLCAN only):'))
    layout.addWidget(bitrate)
    layout.addWidget(QLabel('Optional arguments (refer to Pyuavcan for info):'))
    layout.addWidget(extra_args)
    layout.addWidget(ok)
    layout.setSizeConstraint(layout.SetFixedSize)
    win.setLayout(layout)
    win.exec()

    return result, kwargs
