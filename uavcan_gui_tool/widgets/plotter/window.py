#
# Copyright (C) 2016  UAVCAN Development Team  <uavcan.org>
#
# This software is distributed under the terms of the MIT License.
#
# Author: Pavel Kirienko <pavel.kirienko@zubax.com>
#

from PyQt5.QtWidgets import QMainWindow
from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QColor
from .. import get_app_icon
from .value_extractor import Extractor, Expression, FieldFilter, NodeIDFilter


class PlotterWindow(QMainWindow):
    def __init__(self, get_transfer_callback):
        super(PlotterWindow, self).__init__()
        self.setWindowTitle('UAVCAN Plotter')
        self.setWindowIcon(get_app_icon())

        self._get_transfer = get_transfer_callback

        self._update_timer = QTimer(self)
        self._update_timer.setSingleShot(False)
        self._update_timer.timeout.connect(self._update)
        self._update_timer.start(50)

        self._demo_extractor = Extractor('uavcan.protocol.NodeStatus', Expression('msg.health == msg.HEALTH_OK'),
                                         [NodeIDFilter(125)], QColor('#ffffff'))

    def _update(self):
        while True:
            tr = self._get_transfer()
            if tr:
                extracted = self._demo_extractor.try_extract(tr)
                if extracted:
                    print(extracted)
