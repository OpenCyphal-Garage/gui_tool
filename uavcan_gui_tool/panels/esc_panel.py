#
# Copyright (C) 2016  UAVCAN Development Team  <uavcan.org>
#
# This software is distributed under the terms of the MIT License.
#
# Author: Pavel Kirienko <pavel.kirienko@zubax.com>
#

import uavcan
from functools import partial
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout, QWidget, QLabel, QDialog, QSlider, QLineEdit
from PyQt5.QtCore import QTimer, Qt
from logging import getLogger
from ..widgets import make_icon_button, get_icon

__all__ = 'PANEL_NAME', 'spawn', 'get_icon'

PANEL_NAME = 'ESC Panel'


logger = getLogger(__name__)

_singleton = None


class PercentSlider(QWidget):
    def __init__(self, parent):
        super(PercentSlider, self).__init__(parent)

        self._slider = QSlider(Qt.Vertical, self)
        self._slider.setTickInterval(1)
        self._slider.setMinimum(-100)
        self._slider.setMaximum(100)

        self._zero_button = make_icon_button('hand-stop-o', 'Zero setpoint', self,
                                             on_clicked=lambda: self._slider.setValue(0))

        self._display = QLineEdit(self)
        self._display.setReadOnly(True)

        layout = QVBoxLayout(self)
        layout.addWidget(self._slider)
        layout.addWidget(self._zero_button)
        layout.addWidget(self._display)
        self.setLayout(layout)

    def get_value(self):
        pass

    def slider_moved(self):
        pass


class ESCPanel(QDialog):
    def __init__(self, parent, node):
        super(ESCPanel, self).__init__(parent)
        self.setWindowTitle('ESC Management Panel')
        self.setAttribute(Qt.WA_DeleteOnClose)              # This is required to stop background timers!

        self._node = node

    def __del__(self):
        global _singleton
        _singleton = None

    def closeEvent(self, event):
        global _singleton
        _singleton = None
        super(ESCPanel, self).closeEvent(event)


def spawn(parent, node):
    global _singleton
    if _singleton is None:
        _singleton = ESCPanel(parent, node)

    _singleton.show()
    _singleton.raise_()
    _singleton.activateWindow()

    return _singleton


get_icon = partial(get_icon, 'asterisk')
