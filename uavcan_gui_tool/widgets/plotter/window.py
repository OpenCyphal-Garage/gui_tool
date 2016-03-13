#
# Copyright (C) 2016  UAVCAN Development Team  <uavcan.org>
#
# This software is distributed under the terms of the MIT License.
#
# Author: Pavel Kirienko <pavel.kirienko@zubax.com>
#

import time
from PyQt5.QtWidgets import QMainWindow, QWidget, QVBoxLayout
from PyQt5.QtCore import QTimer, Qt
from .. import get_app_icon, make_icon_button
from .plot_areas import PLOT_AREAS
from .plot_container import PlotContainerWidget


class PlotterWindow(QMainWindow):
    def __init__(self, get_transfer_callback):
        super(PlotterWindow, self).__init__()
        self.setWindowTitle('UAVCAN Plotter')
        self.setWindowIcon(get_app_icon())

        self._active_data_types = set()

        self._get_transfer = get_transfer_callback

        self._update_timer = QTimer(self)
        self._update_timer.setSingleShot(False)
        self._update_timer.timeout.connect(self._update)
        self._update_timer.start(50)

        self._base_time = time.monotonic()

        self._cont = PlotContainerWidget(self, PLOT_AREAS['Y-T plot'], self._active_data_types)

        self.addDockWidget(Qt.BottomDockWidgetArea, self._cont)
        self.statusBar().show()

        self.resize(800, 600)

    def _update(self):
        while True:
            tr = self._get_transfer()
            if not tr:
                break

            self._active_data_types.add(tr.data_type_name)

            self._cont.process_transfer(tr.ts_mono - self._base_time, tr)

        self._cont.update()
