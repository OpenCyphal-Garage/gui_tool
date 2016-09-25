#
# Copyright (C) 2016  UAVCAN Development Team  <uavcan.org>
#
# This software is distributed under the terms of the MIT License.
#
# Author: Pavel Kirienko <pavel.kirienko@zubax.com>
#

import uavcan
from functools import partial
from PyQt5.QtWidgets import QGroupBox, QVBoxLayout, QHBoxLayout, QWidget, QLabel, QDialog
from PyQt5.QtCore import QTimer, Qt
from logging import getLogger
from ..widgets import make_icon_button, get_icon


PANEL_NAME = 'ESC Panel'


logger = getLogger(__name__)


class ESCPanel(QDialog):
    def __init__(self, parent, node):
        super(ESCPanel, self).__init__(parent)
        self.setWindowTitle(self.WINDOW_NAME_PREFIX)
        self.setAttribute(Qt.WA_DeleteOnClose)              # This is required to stop background timers!

        self._node = node


def spawn(parent, node):
    pass


get_icon = partial(get_icon, 'asterisk')
