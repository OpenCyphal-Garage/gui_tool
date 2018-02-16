#
# Copyright (C) 2016  UAVCAN Development Team  <uavcan.org>
#
# This software is distributed under the terms of the MIT License.
#
# Author: Pavel Kirienko <pavel.kirienko@zubax.com>
#

import os
import sys
import glob
import time
import threading
import copy
from .widgets import show_error, get_monospace_font
from PyQt5.QtWidgets import (
    QComboBox,
    QCompleter,
    QDialog,
    QDirModel,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QIntValidator
from logging import getLogger
from collections import OrderedDict
from itertools import count


STANDARD_BAUD_RATES = 9600, 115200, 460800, 921600, 1000000, 3000000
DEFAULT_BAUD_RATE = 115200
assert DEFAULT_BAUD_RATE in STANDARD_BAUD_RATES


RUNNING_ON_LINUX = 'linux' in sys.platform.lower()


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

    return re.findall(r'\d+?: ([a-z0-9]+?): <[^>]*UP[^>]*>.*\n *link/can', out) + out_ifaces


def list_ifaces():
    """Returns dictionary, where key is description, value is the OS assigned name of the port"""
    logger.debug('Updating iface list...')
    if RUNNING_ON_LINUX:
        # Linux system
        ifaces = glob.glob('/dev/serial/by-id/*')
        try:
            ifaces = list(sorted(ifaces,
                                 key=lambda s: not ('zubax' in s.lower() and 'babel' in s.lower())))
        except Exception:
            logger.warning('Sorting failed', exc_info=True)

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
        from PyQt5 import QtSerialPort

        out = OrderedDict()
        for port in QtSerialPort.QSerialPortInfo.availablePorts():
            out[port.description()] = port.systemLocation()

        return out


class BackgroundIfaceListUpdater:
    UPDATE_INTERVAL = 0.5

    def __init__(self):
        self._ifaces = list_ifaces()
        self._thread = threading.Thread(target=self._run, name='iface_lister', daemon=True)
        self._keep_going = True
        self._lock = threading.Lock()

    def __enter__(self):
        logger.debug('Starting iface list updater')
        self._thread.start()
        return self

    def __exit__(self, *_):
        logger.debug('Stopping iface list updater...')
        self._keep_going = False
        self._thread.join()
        logger.debug('Stopped iface list updater')

    def _run(self):
        while self._keep_going:
            time.sleep(self.UPDATE_INTERVAL)
            new_list = list_ifaces()
            with self._lock:
                self._ifaces = new_list

    def get_list(self):
        with self._lock:
            return copy.copy(self._ifaces)

class DirectorySelectionWidget(QWidget):
    def __init__(self, parent):
        super().__init__()
        self.dir_selection = os.path.abspath(os.curdir)
        dir_textbox = QLineEdit(parent)
        dir_textbox.setText(self.dir_selection)

        dir_text_completer = QCompleter(parent)
        dir_text_completer.setCaseSensitivity(Qt.CaseSensitive)
        dir_text_completer.setModel(QDirModel(parent))
        dir_textbox.setCompleter(dir_text_completer)

        def on_edit():
            nonlocal dir_textbox
            self.dir_selection = str(dir_textbox.text())

        dir_textbox.textChanged.connect(on_edit)

        dir_browser = QPushButton('Browse', parent)

        def on_browse():
            self.dir_selection = str(QFileDialog.getExistingDirectory(parent, "Select Directory"))
            dir_textbox.setText(self.dir_selection)

        dir_browser.clicked.connect(on_browse)

        layout = QHBoxLayout(parent)
        layout.addWidget(dir_textbox)
        layout.addWidget(dir_browser)

        self.setLayout(layout)

    def selection(self):
        return self.dir_selection


def run_setup_window(icon):
    win = QDialog()
    win.setWindowTitle('Setup')
    win.setWindowIcon(icon)
    win.setWindowFlags(Qt.CustomizeWindowHint | Qt.WindowTitleHint | Qt.WindowCloseButtonHint)
    win.setAttribute(Qt.WA_DeleteOnClose)              # This is required to stop background timers!

    combo = QComboBox(win)
    combo.setEditable(True)
    combo.setInsertPolicy(QComboBox.NoInsert)
    combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
    combo.setFont(get_monospace_font())

    combo_completer = QCompleter()
    combo_completer.setCaseSensitivity(Qt.CaseSensitive)
    combo_completer.setModel(combo.model())
    combo.setCompleter(combo_completer)

    bitrate = QSpinBox(win)
    bitrate.setMaximum(1000000)
    bitrate.setMinimum(10000)
    bitrate.setValue(1000000)

    baudrate = QComboBox(win)
    baudrate.setEditable(True)
    baudrate.setInsertPolicy(QComboBox.NoInsert)
    baudrate.setSizeAdjustPolicy(QComboBox.AdjustToContents)
    baudrate.setFont(get_monospace_font())

    baudrate_completer = QCompleter(win)
    baudrate_completer.setModel(baudrate.model())
    baudrate.setCompleter(baudrate_completer)

    baudrate.setValidator(QIntValidator(min(STANDARD_BAUD_RATES), max(STANDARD_BAUD_RATES)))
    baudrate.insertItems(0, map(str, STANDARD_BAUD_RATES))
    baudrate.setCurrentText(str(DEFAULT_BAUD_RATE))

    dir_selection = DirectorySelectionWidget(win)

    ok = QPushButton('OK', win)

    def update_slcan_options_visibility():
        if RUNNING_ON_LINUX:
            slcan_active = '/' in combo.currentText()
        else:
            slcan_active = True
        slcan_group.setEnabled(slcan_active)

    combo.currentTextChanged.connect(update_slcan_options_visibility)

    ifaces = None

    def update_iface_list():
        nonlocal ifaces
        ifaces = iface_lister.get_list()
        known_keys = set()
        remove_indices = []
        was_empty = combo.count() == 0
        # Marking known and scheduling for removal
        for idx in count():
            tx = combo.itemText(idx)
            if not tx:
                break
            known_keys.add(tx)
            if tx not in ifaces:
                logger.debug('Removing iface %r', tx)
                remove_indices.append(idx)
        # Removing - starting from the last item in order to retain indexes
        for idx in remove_indices[::-1]:
            combo.removeItem(idx)
        # Adding new items - starting from the last item in order to retain the final order
        for key in list(ifaces.keys())[::-1]:
            if key not in known_keys:
                logger.debug('Adding iface %r', key)
                combo.insertItem(0, key)
        # Updating selection
        if was_empty:
            combo.setCurrentIndex(0)

    result = None
    kwargs = {}

    def on_ok():
        nonlocal result, kwargs
        try:
            baud_rate_value = int(baudrate.currentText())
        except ValueError:
            show_error('Invalid parameters', 'Could not parse baud rate', 'Please specify correct baud rate',
                       parent=win)
            return
        if not (min(STANDARD_BAUD_RATES) <= baud_rate_value <= max(STANDARD_BAUD_RATES)):
            show_error('Invalid parameters', 'Baud rate is out of range',
                       'Baud rate value should be within [%s, %s]' %
                       (min(STANDARD_BAUD_RATES), max(STANDARD_BAUD_RATES)),
                       parent=win)
            return
        kwargs['baudrate'] = baud_rate_value
        kwargs['bitrate'] = int(bitrate.value())
        result_key = str(combo.currentText()).strip()
        if not result_key:
            show_error('Invalid parameters', 'Interface name cannot be empty', 'Please select a valid interface',
                       parent=win)
            return
        try:
            result = ifaces[result_key]
        except KeyError:
            result = result_key
        win.close()

    ok.clicked.connect(on_ok)

    layout = QVBoxLayout(win)
    layout.addWidget(QLabel('Select CAN interface'))
    layout.addWidget(combo)

    slcan_group = QGroupBox('SLCAN adapter settings', win)
    slcan_layout = QVBoxLayout(slcan_group)

    slcan_layout.addWidget(QLabel('CAN bus bit rate:'))
    slcan_layout.addWidget(bitrate)
    slcan_layout.addWidget(QLabel('Adapter baud rate (not applicable to USB-CAN adapters):'))
    slcan_layout.addWidget(baudrate)

    slcan_group.setLayout(slcan_layout)

    layout.addWidget(slcan_group)

    layout.addWidget(QLabel('Select custom DSDL'))
    layout.addWidget(dir_selection)

    layout.addWidget(ok)
    layout.setSizeConstraint(layout.SetFixedSize)
    win.setLayout(layout)

    with BackgroundIfaceListUpdater() as iface_lister:
        update_slcan_options_visibility()
        update_iface_list()
        timer = QTimer(win)
        timer.setSingleShot(False)
        timer.timeout.connect(update_iface_list)
        timer.start(int(BackgroundIfaceListUpdater.UPDATE_INTERVAL / 2 * 1000))
        win.exec()

    return result, kwargs, dir_selection.selection()
