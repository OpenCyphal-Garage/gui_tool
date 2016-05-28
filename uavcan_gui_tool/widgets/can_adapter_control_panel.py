#
# Copyright (C) 2016  UAVCAN Development Team  <uavcan.org>
#
# This software is distributed under the terms of the MIT License.
#
# Author: Pavel Kirienko <pavel.kirienko@zubax.com>
#

import re
import os
from PyQt5.QtWidgets import QLabel, QDoubleSpinBox, QHBoxLayout, QVBoxLayout, QDialog, QTabWidget, QWidget, \
    QCheckBox, QStatusBar, QProgressDialog, QMessageBox, QHeaderView, QTableWidgetItem
from PyQt5.QtCore import QTimer
from logging import getLogger
import yaml

from . import make_icon_button, get_icon, BasicTable, get_monospace_font


logger = getLogger(__name__)


class StateTable(BasicTable):
    COLUMNS = [
        BasicTable.Column('Parameter',
                          lambda e: e[0]),
        BasicTable.Column('Value',
                          lambda e: e[1],
                          resize_mode=QHeaderView.Stretch),
    ]

    def __init__(self, parent):
        super(StateTable, self).__init__(parent, self.COLUMNS, font=get_monospace_font())

    def update_state(self, key_value_list):
        self.setUpdatesEnabled(False)

        existing_keys = [self.item(x, 0).text() for x in range(self.rowCount())]
        new_keys = [str(k) for k, _ in key_value_list]

        if existing_keys == new_keys:
            for row in range(self.rowCount()):
                self.setItem(row, 1, QTableWidgetItem(str(key_value_list[row][1])))
        else:
            self.clear()
            self.setRowCount(len(key_value_list))
            for i, kv in enumerate(key_value_list):
                self.set_row(i, kv)

        self.setUpdatesEnabled(True)


class ConfigurationParameter:
    def __init__(self, name, value, default, minimum, maximum):
        self.name = name
        self.value = value
        self.default = default
        self.minimum = minimum
        self.maximum = maximum

        def cast(what, to):
            return to(what) if what is not None else None

        # noinspection PyChainedComparisons
        if isinstance(self.value, int) and 0 <= self.value <= 1 and self.minimum == 0 and self.maximum == 1:
            self.type = bool
            self.value = bool(self.value)
        elif isinstance(self.value, int):
            self.type = int
        elif isinstance(self.value, float):
            self.type = float
        else:
            raise ValueError('Invalid value type')

        self.default = cast(self.default, self.type)
        self.minimum = cast(self.minimum, self.type)
        self.maximum = cast(self.maximum, self.type)

    def __str__(self):
        s = '%s = ' % self.name
        s += ('%d' if self.type in (bool, int) else '%s') % self.value
        if self.minimum is not None:
            s += (' [%d, %d]' if self.type in (bool, int) else ' [%s, %s]') % (self.minimum, self.maximum)
        if self.default is not None:
            s += (' (%d)' if self.type in (bool, int) else ' (%s)') % self.default
        return s

    __repr__ = __str__

    @staticmethod
    def parse_cli_response_line(line):
        # Examples:
        # uart.baudrate = 115200 [2400, 3000000] (115200)
        # uart.baudrate = 115200 [2400, 3000000]
        # uart.baudrate = 115200
        # uart.baudrate = 115200 (115200)
        # Q: Why couldn't Chris try out the regular expressions he created until he left home?
        # A: His mom wouldn't let him play with matches.
        pattern = r'(?m)^\s*(\S+)\s*=\s*([^\s\[\(]+)\s*(?:\[(\S+),\s*(\S+)\])?\s*(?:\((\S+)\))?'
        (name, value, minimum, maximum, default), = re.findall(pattern, line)

        if not name or not value:
            raise ValueError('Invalid parameter string %r: name or value could not be parsed' % line)

        try:
            value = eval(value)
            minimum, maximum, default = [(eval(x) if x else None) for x in (minimum, maximum, default)]
        except Exception as ex:
            raise ValueError('Could not parse parameter string %r' % line) from ex

        if (minimum is None) != (maximum is None):
            raise ValueError('Invalid parameter string %r: minimum or maximum cannot be set separately' % line)

        return ConfigurationParameter(name=name,
                                      value=value,
                                      default=default,
                                      minimum=minimum,
                                      maximum=maximum)


class ConfigurationTable(BasicTable):
    COLUMNS = [
        BasicTable.Column('Name',
                          lambda e: e.name),
        BasicTable.Column('Value',
                          lambda e: e.value),
        BasicTable.Column('Default',
                          lambda e: e.default),
        BasicTable.Column('Min',
                          lambda e: e.minimum),
        BasicTable.Column('Max',
                          lambda e: e.maximum),
    ]

    def __init__(self, parent):
        super(ConfigurationTable, self).__init__(parent, self.COLUMNS, font=get_monospace_font())

    def reload(self, params):
        pass


class StateWidget(QWidget):
    def __init__(self, parent, cli_iface):
        super(StateWidget, self).__init__(parent)

        self._cli_iface = cli_iface

        self._table = StateTable(self)

        self._reload_button = make_icon_button('refresh', 'Reload state information from the adapter', self,
                                               on_clicked=self._do_reload, text='Reload')

        self._auto_reload_checkbox = QCheckBox('Auto reload every [sec]:', self)
        self._auto_reload_checkbox.stateChanged.connect(self._update_auto_reload)

        self._auto_reload_spinbox = QDoubleSpinBox(self)
        self._auto_reload_spinbox.setDecimals(1)
        self._auto_reload_spinbox.setMinimum(0.5)
        self._auto_reload_spinbox.setMaximum(10)
        self._auto_reload_spinbox.setValue(1)
        self._auto_reload_spinbox.setSingleStep(0.5)
        self._auto_reload_spinbox.setToolTip('Auto reload interval, in seconds')
        self._auto_reload_spinbox.valueChanged.connect(self._update_auto_reload)

        self._auto_reload_timer = QTimer(self)
        self._auto_reload_timer.setSingleShot(False)
        self._auto_reload_timer.timeout.connect(self._do_reload)

        layout = QVBoxLayout(self)

        buttons_layout = QHBoxLayout(self)
        buttons_layout.addWidget(self._reload_button, 1)
        buttons_layout.addWidget(self._auto_reload_checkbox)
        buttons_layout.addWidget(self._auto_reload_spinbox)

        layout.addLayout(buttons_layout)
        layout.addWidget(self._table, 1)
        self.setLayout(layout)

    def _update_auto_reload(self):
        enabled = self._auto_reload_checkbox.isChecked()
        if enabled:
            interval = float(self._auto_reload_spinbox.value())
            self._auto_reload_timer.start(int(interval * 1e3 + 0.5))
            self.window().show_message('Auto reload interval %0.1f seconds', interval)
        else:
            self._auto_reload_timer.stop()
            self.window().show_message('Auto reload stopped')

    def _do_reload(self):
        self.window().show_message('State requested...')

        def proxy(kv):
            if isinstance(kv, Exception):
                self.window().show_message('State request failed: %r', kv)
            elif kv is None:
                self.window().show_message('State request timed out')
            else:
                self.window().show_message('State request succeeded')
                self._table.update_state(kv)

        self._cli_iface.request_state(proxy)


class ConfigurationWidget(QWidget):
    def __init__(self, parent):
        super(ConfigurationWidget, self).__init__(parent)

        self._table = ConfigurationTable(self)

        self._fetch_button = make_icon_button('refresh',
                                              'Fetch configuration from the adapter; local changes will be lost',
                                              self, on_clicked=self._do_fetch, text='Fetch')

        self._store_button = make_icon_button('database',
                                              'Send configuration to the adapter',
                                              self, on_clicked=self._do_store, text='Store')

        self._erase_button = make_icon_button('eraser',
                                              'Erase configuration on the adapter',
                                              self, on_clicked=self._do_erase, text='Erase')

        layout = QVBoxLayout(self)

        buttons_layout = QHBoxLayout(self)
        buttons_layout.addWidget(self._fetch_button)
        buttons_layout.addWidget(self._store_button)
        buttons_layout.addWidget(self._erase_button)

        layout.addLayout(buttons_layout)
        layout.addWidget(self._table, 1)
        self.setLayout(layout)

    def _do_fetch(self):
        pass

    def _do_store(self):
        pass

    def _do_erase(self):
        pass


class SLCANCLIWidget(QWidget):
    def __init__(self, parent, cli_iface):
        super(SLCANCLIWidget, self).__init__(parent)

        self._cli_iface = cli_iface


class SLCANControlPanel(QDialog):
    def __init__(self, parent, cli_iface, iface_name):
        super(SLCANControlPanel, self).__init__(parent)
        self.setWindowTitle('SLCAN Adapter Control Panel')

        self._cli_iface = cli_iface
        self._iface_name = iface_name

        self._state_widget = StateWidget(self, self._cli_iface)
        self._config_widget = ConfigurationWidget(self)

        self._tab_widget = QTabWidget(self)
        self._tab_widget.addTab(self._state_widget, get_icon('dashboard'), 'Adapter State')
        self._tab_widget.addTab(self._config_widget, get_icon('wrench'), 'Configuration')

        self._status_bar = QStatusBar(self)
        self._status_bar.setSizeGripEnabled(False)

        iface_name_label = QLabel(iface_name.split('/')[-1], self)
        iface_name_label.setFont(get_monospace_font())

        layout = QVBoxLayout(self)
        layout.addWidget(iface_name_label)
        layout.addWidget(self._tab_widget)
        layout.addWidget(self._status_bar)

        left, top, right, bottom = layout.getContentsMargins()
        bottom = 0
        layout.setContentsMargins(left, top, right, bottom)

        self.setLayout(layout)

    def show_message(self, text, *fmt, duration=0):
        self._status_bar.showMessage(text % fmt, duration * 1000)


class SLCANCLIInterface:
    def __init__(self, driver):
        self._driver = driver

    def check_is_interface_supported(self, callback):
        def proxy(resp):
            logger.info('SLCANCLIInterface.check_is_interface_supported() response: %r', resp)
            callback(not resp.expired)

        self._driver.execute_cli_command('stat', proxy)

    def request_state(self, callback):
        def proxy(resp):
            if resp.expired:
                callback(None)
            else:
                try:
                    values = [yaml.load(x) for x in resp.lines]
                    output = []
                    for kv in values:
                        for k, v in kv.items():
                            output.append((k, v))
                    callback(output)
                except Exception as ex:
                    callback(ex)

        self._driver.execute_cli_command('stat', proxy)

    def request_all_config_params(self, callback):
        pass

    def store_all_config_params(self, callback):
        pass

    def erase_all_config_params(self, callback):
        pass

    def set_config_param(self, name, value, callback):
        pass

    def execute_raw_command(self, command, callback):
        def proxy(resp):
            if resp.expired:
                callback(None)
            else:
                lines = os.linesep.join(resp.lines)
                callback(lines)

        self._driver.execute_cli_command(command, proxy)

    @staticmethod
    def is_backend_supported(driver):
        return hasattr(driver, 'execute_cli_command')


def spawn_window(parent, node, iface_name):
    driver = node.can_driver

    if not SLCANCLIInterface.is_backend_supported(driver):
        mbox = QMessageBox(parent)
        mbox.setWindowTitle('Unsupported CAN Backend')
        mbox.setText('CAN Adapter Control Panel cannot be used with the current CAN backend.')
        mbox.setInformativeText('The current backend is %r.' % type(driver).__name__)
        mbox.setIcon(QMessageBox.Information)
        mbox.setStandardButtons(QMessageBox.Ok)
        mbox.exec()
        return

    progress_dialog = QProgressDialog(parent)
    progress_dialog.setWindowTitle('CAN Adapter Control Panel Initialization')
    progress_dialog.setLabelText('Detecting CAN adapter capabilities...')
    progress_dialog.setMinimumDuration(800)
    progress_dialog.setCancelButton(None)
    progress_dialog.setRange(0, 0)
    progress_dialog.show()

    def supported_callback(supported):
        progress_dialog.close()

        if not supported:
            mbox = QMessageBox(parent)
            mbox.setWindowTitle('Incompatible CAN Adapter')
            mbox.setText('CAN Adapter Control Panel cannot be used with the connected adapter.')
            mbox.setInformativeText('Connected SLCAN adapter does not support CLI extensions.')
            mbox.setIcon(QMessageBox.Information)
            mbox.setStandardButtons(QMessageBox.Ok)
            mbox.exec()
            return

        slcp = SLCANControlPanel(parent, slcan_iface, iface_name)
        slcp.show()

    slcan_iface = SLCANCLIInterface(driver)
    slcan_iface.check_is_interface_supported(supported_callback)
