#
# Copyright (C) 2016  UAVCAN Development Team  <uavcan.org>
#
# This software is distributed under the terms of the MIT License.
#
# Author: Pavel Kirienko <pavel.kirienko@zubax.com>
#

import re
from PyQt5.QtWidgets import QGroupBox, QLabel, QSpinBox, QHBoxLayout, QVBoxLayout, QDialog, QTabWidget, QWidget
from PyQt5.QtCore import QTimer
from logging import getLogger

from . import make_icon_button, get_icon, BasicTable, get_monospace_font


logger = getLogger(__name__)


class StateTable(BasicTable):
    COLUMNS = [
        BasicTable.Column('Parameter',
                          lambda e: e[0]),
        BasicTable.Column('Value',
                          lambda e: e[1]),
    ]

    def __init__(self, parent):
        super(StateTable, self).__init__(parent, self.COLUMNS, font=get_monospace_font())

    def update_state(self, state_dict):
        pass


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
    def __init__(self, parent):
        super(StateWidget, self).__init__(parent)

        self._table = StateTable(self)

        self._reload_button = make_icon_button('refresh', 'Reload state information from the adapter', self,
                                               on_clicked=self._do_reload, text='Reload')

        layout = QVBoxLayout(self)
        layout.addWidget(self._table, 1)
        layout.addWidget(self._reload_button)
        self.setLayout(layout)

    def _do_reload(self):
        pass


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
        layout.addWidget(self._table)

        buttons_layout = QHBoxLayout(self)
        buttons_layout.addWidget(self._fetch_button)
        buttons_layout.addWidget(self._store_button)
        buttons_layout.addWidget(self._erase_button)

        layout.addLayout(buttons_layout)
        self.setLayout(layout)

    def _do_fetch(self):
        pass

    def _do_store(self):
        pass

    def _do_erase(self):
        pass


class CANAdapterControlPanel(QDialog):
    def __init__(self, parent, node, iface_name):
        super(CANAdapterControlPanel, self).__init__(parent)
        self.setWindowTitle('CAN Adapter Control Panel')

        self._node = node
        self._iface_name = iface_name

        self._iface_label = QLabel(iface_name, self)

        self._state_widget = StateWidget(self)
        self._config_widget = ConfigurationWidget(self)

        self._tab_widget = QTabWidget(self)
        self._tab_widget.addTab(self._state_widget, get_icon('dashboard'), 'Adapter State')
        self._tab_widget.addTab(self._config_widget, get_icon('wrench'), 'Configuration')

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel('Adapter ' + iface_name, self))
        layout.addWidget(self._tab_widget)
        self.setLayout(layout)
