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
    QCheckBox, QStatusBar, QHeaderView, QTableWidgetItem, QSpinBox, QLineEdit, QComboBox, QCompleter, QPlainTextEdit
from PyQt5.QtCore import QTimer, Qt
from logging import getLogger
import yaml

from .. import make_icon_button, get_icon, BasicTable, get_monospace_font, show_error, CommitableComboBoxWithHistory, \
    request_confirmation


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

        # noinspection PyCallByClass,PyTypeChecker
        QTimer.singleShot(100, self._do_reload)

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
        logger.debug('Reloading state...')
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


class ConfigParam:
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

        return ConfigParam(name=name, value=value, default=default, minimum=minimum, maximum=maximum)


class ConfigParamEditWindow(QDialog):
    def __init__(self, parent, model, cli_iface, store_callback):
        super(ConfigParamEditWindow, self).__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setWindowTitle('Edit Parameter')
        self.setModal(True)

        self._model = model
        self._cli_iface = cli_iface
        self._store_callback = store_callback

        name_label = QLabel(model.name, self)
        name_label.setFont(get_monospace_font())

        if model.type is bool:
            self._value = QCheckBox(self)
            self._value.setChecked(model.value)
        elif model.type is int:
            self._value = QSpinBox(self)
            if model.minimum is not None:
                self._value.setRange(model.minimum,
                                     model.maximum)
            else:
                self._value.setRange(-0x80000000,
                                     +0x7FFFFFFF)
            self._value.setValue(model.value)
        elif model.type is float:
            self._value = QDoubleSpinBox(self)
            if model.minimum is not None:
                self._value.setRange(model.minimum,
                                     model.maximum)
            else:
                self._value.setRange(-3.4028235e+38,
                                     +3.4028235e+38)
            self._value.setValue(model.value)
        elif model.type is str:
            self._value = QLineEdit(self)
            self._value.setText(model.value)
        else:
            raise ValueError('Unsupported value type %r' % model.type)

        self._ok_button = make_icon_button('check', 'Send changes to the device', self,
                                           text='OK', on_clicked=self._do_ok)

        self._cancel_button = make_icon_button('remove', 'Discard changes and close this window', self,
                                               text='Cancel', on_clicked=self.close)

        layout = QVBoxLayout(self)

        value_layout = QHBoxLayout(self)
        value_layout.addWidget(name_label)
        value_layout.addWidget(self._value, 1)

        controls_layout = QHBoxLayout(self)
        controls_layout.addWidget(self._cancel_button)
        controls_layout.addWidget(self._ok_button)

        layout.addLayout(value_layout)
        layout.addLayout(controls_layout)
        self.setLayout(layout)

    def _do_ok(self):
        if self._model.type is bool:
            value = self._value.isChecked()
        elif self._model.type is int or self._model.type is float:
            value = self._value.value()
        else:
            value = self._value.text()

        self._store_callback(value)
        self.close()


class ConfigWidget(QWidget):
    COLUMNS = [
        BasicTable.Column('Name',
                          lambda e: e.name),
        BasicTable.Column('Value',
                          lambda e: e.value,
                          resize_mode=QHeaderView.Stretch),
        BasicTable.Column('Default',
                          lambda e: e.default),
        BasicTable.Column('Min',
                          lambda e: e.minimum if e.type is not bool else ''),
        BasicTable.Column('Max',
                          lambda e: e.maximum if e.type is not bool else ''),
    ]

    def __init__(self, parent, cli_iface):
        super(ConfigWidget, self).__init__(parent)

        self._cli_iface = cli_iface

        self._table = BasicTable(self, self.COLUMNS, font=get_monospace_font())
        self._table.cellDoubleClicked.connect(lambda row, col: self._do_edit_param(row))
        self._parameters = []

        self._have_unsaved_changes = False

        self._fetch_button = make_icon_button('refresh',
                                              'Fetch configuration from the adapter',
                                              self, on_clicked=self._do_fetch, text='Fetch')

        self._store_button = make_icon_button('database',
                                              'Store the current configuration into non-volatile memory on the adapter',
                                              self, on_clicked=self._do_store, text='Store')

        self._erase_button = make_icon_button('eraser',
                                              'Erase configuration from the non-volatile memory',
                                              self, on_clicked=self._do_erase, text='Erase')

        layout = QVBoxLayout(self)

        buttons_layout = QHBoxLayout(self)
        buttons_layout.addWidget(self._fetch_button)
        buttons_layout.addWidget(self._store_button)
        buttons_layout.addWidget(self._erase_button)

        layout.addWidget(QLabel('Double click to change parameter value.', self))
        layout.addLayout(buttons_layout)
        layout.addWidget(self._table, 1)
        self.setLayout(layout)

        # noinspection PyCallByClass,PyTypeChecker
        QTimer.singleShot(100, self._do_fetch)

    @property
    def have_unsaved_changes(self):
        return self._have_unsaved_changes

    def _do_edit_param(self, index):
        def callback(value):
            try:
                self._cli_iface.set_config_param(self._parameters[index].name, value, self._show_callback_result)
                # noinspection PyCallByClass,PyTypeChecker
                QTimer.singleShot(10, self._do_fetch)
            except Exception as ex:
                show_error('Parameter Change Error', 'Could request parameter change.', ex, self)
            else:
                self._have_unsaved_changes = True
                # noinspection PyCallByClass,PyTypeChecker
                QTimer.singleShot(2000, lambda:
                    self.window().show_message('Click "Store" to make your configuration changes persistent'))

        try:
            win = ConfigParamEditWindow(self, self._parameters[index], self._cli_iface, callback)
            win.show()
        except Exception as ex:
            show_error('Parameter Dialog Error', 'Could not open parameter edit dialog.', ex, self)

    def _show_callback_result(self, result):
        if isinstance(result, Exception):
            self.window().show_message('Operation failed: %r', result)
        elif not result:
            self.window().show_message('Operation timed out')
        else:
            self.window().show_message('Success')

    def _do_fetch(self):
        def callback(params):
            self._table.setUpdatesEnabled(False)
            self._table.clear()
            self._parameters = []

            if params is None:
                self.window().show_message('Configuration parameters request timed out')
            elif isinstance(params, Exception):
                self.window().show_message('Configuration parameters request failed: %r', params)
            else:
                self.window().show_message('Configuration parameters request succeeded')
                self._parameters = params
                self._table.setRowCount(len(params))
                for row, par in enumerate(params):
                    self._table.set_row(row, par)

            self._table.setUpdatesEnabled(True)

        self._table.clear()
        self._cli_iface.request_all_config_params(callback)

    def _do_store(self):
        self._cli_iface.store_all_config_params(self._show_callback_result)
        self._have_unsaved_changes = False

    def _do_erase(self):
        self._cli_iface.erase_all_config_params(self._show_callback_result)
        self._have_unsaved_changes = False


class CLIWidget(QWidget):
    def __init__(self, parent, cli_iface):
        super(CLIWidget, self).__init__(parent)

        self._cli_iface = cli_iface

        self._command_line = CommitableComboBoxWithHistory(self)
        self._command_line.setToolTip('Enter the command here')
        self._command_line.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self._command_line.setFont(get_monospace_font())
        self._command_line.on_commit = self._do_execute

        self._command_line_completer = QCompleter()
        self._command_line_completer.setCaseSensitivity(Qt.CaseSensitive)
        self._command_line_completer.setModel(self._command_line.model())

        self._command_line.setCompleter(self._command_line_completer)

        self._execute_button = make_icon_button('flash', 'Execute command', self, on_clicked=self._do_execute)

        self._response_box = QPlainTextEdit(self)
        self._response_box.setToolTip('Command output will be printed here')
        self._response_box.setReadOnly(True)
        self._response_box.setLineWrapMode(QPlainTextEdit.NoWrap)
        self._response_box.setFont(get_monospace_font())
        self._response_box.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        try:
            self._log_viewer.setPlaceholderText('Command output will be printed here')
        except AttributeError:      # Old PyQt
            pass

        layout = QVBoxLayout(self)

        controls_layout = QHBoxLayout(self)
        controls_layout.addWidget(self._command_line, 1)
        controls_layout.addWidget(self._execute_button)

        layout.addLayout(controls_layout)
        layout.addWidget(self._response_box, 1)
        self.setLayout(layout)

    def _do_execute(self):
        self._response_box.clear()

        command = self._command_line.currentText()
        if not command.strip():
            return

        self._command_line.add_current_text_to_history()

        def callback(lines):
            self.setEnabled(True)
            if lines is None:
                self.window().show_message('Command response timed out')
                self._response_box.setPlainText('<RESPONSE TIMED OUT>')
            else:
                self.window().show_message('Command response received')
                self._response_box.setPlainText(lines)

        self.setEnabled(False)
        self._cli_iface.execute_raw_command(command, callback)


class ControlPanelWindow(QDialog):
    def __init__(self, parent, cli_iface, iface_name):
        super(ControlPanelWindow, self).__init__(parent)
        self.setWindowTitle('SLCAN Adapter Control Panel')
        self.setAttribute(Qt.WA_DeleteOnClose)              # This is required to stop background timers!

        self._cli_iface = cli_iface
        self._iface_name = iface_name

        self._state_widget = StateWidget(self, self._cli_iface)
        self._config_widget = ConfigWidget(self, self._cli_iface)
        self._cli_widget = CLIWidget(self, self._cli_iface)

        self._tab_widget = QTabWidget(self)
        self._tab_widget.addTab(self._state_widget, get_icon('dashboard'), 'Adapter State')
        self._tab_widget.addTab(self._config_widget, get_icon('wrench'), 'Configuration')
        self._tab_widget.addTab(self._cli_widget, get_icon('terminal'), 'Command Line')

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
        self.resize(400, 400)

    def closeEvent(self, close_event):
        if self._config_widget.have_unsaved_changes:
            if request_confirmation('Save changes?',
                                    'You made changes to the adapter configuration that were not saved. '
                                    'Do you want to go back and save them?',
                                    parent=self):
                close_event.ignore()
                self._tab_widget.setCurrentWidget(self._config_widget)
                return

        super(ControlPanelWindow, self).closeEvent(close_event)

    def show_message(self, text, *fmt, duration=0):
        self._status_bar.showMessage(text % fmt, duration * 1000)


class CLIInterface:
    def __init__(self, driver):
        self._driver = driver

    def check_is_interface_supported(self, callback):
        def proxy(resp):
            logger.info('CLIInterface.check_is_interface_supported() response: %r', resp)
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
        def proxy(resp):
            if resp.expired:
                callback(None)
            else:
                try:
                    output = [ConfigParam.parse_cli_response_line(x) for x in resp.lines]
                    logger.info('Adapter config params: %r', output)
                    callback(output)
                except Exception as ex:
                    callback(ex)

        self._driver.execute_cli_command('cfg list', proxy)

    @staticmethod
    def _make_binary_proxy(callback):
        def proxy(resp):
            if resp.expired:
                callback(None)
            else:
                if len(resp.lines) > 0:
                    callback(Exception('Unexpected response: %r' % resp.lines))
                else:
                    callback(True)

        return proxy

    def store_all_config_params(self, callback):
        self._driver.execute_cli_command('cfg save', self._make_binary_proxy(callback))

    def erase_all_config_params(self, callback):
        self._driver.execute_cli_command('cfg erase', self._make_binary_proxy(callback))

    def set_config_param(self, name, value, callback):
        if isinstance(value, (bool, int)):
            value = '%d' % value
        elif isinstance(value, float):
            value = '%.9f' % value
        elif isinstance(value, str):
            pass
        else:
            raise ValueError('Unexpected value type: %r' % type(value))

        line = 'cfg set %s %s' % (name, value)

        self._driver.execute_cli_command(line, self._make_binary_proxy(callback))

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
