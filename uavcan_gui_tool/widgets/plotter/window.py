#
# Copyright (C) 2016  UAVCAN Development Team  <uavcan.org>
#
# This software is distributed under the terms of the MIT License.
#
# Author: Pavel Kirienko <pavel.kirienko@zubax.com>
#

import time
from PyQt5.QtWidgets import QMainWindow, QWidget, QVBoxLayout
from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QColor
from .. import get_app_icon, make_icon_button
from .value_extractor import Extractor, Expression
from .value_extractor_views import NewValueExtractorWindow, ExtractorWidget
from .plot_areas import PLOT_AREAS


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

        central_widget = QWidget(self)
        layout = QVBoxLayout(central_widget)

        self._base_time = time.monotonic()

        self._plot_yt = PLOT_AREAS['Y-T plot'](self)
        self._plot_xy = PLOT_AREAS['X-Y plot'](self)

        self._demo_extractor = Extractor('uavcan.equipment.gnss.Fix',
                                         #Expression('msg.longitude_deg_1e8 / 1e8'),
                                         Expression('1, 2, 3, 4, 5, 6, 7, 8, 9'),
                                         [Expression('src_node_id == 125')],
                                         QColor('#ff00ff'))

        self._demo_extractor2 = Extractor('uavcan.equipment.gnss.Fix',
                                          Expression('msg.longitude_deg_1e8 / 1e8, msg.latitude_deg_1e8 / 1e8'),
                                          [Expression('src_node_id == 125')],
                                          QColor('#00ffff'))

        layout.addWidget(self._plot_yt)
        layout.addWidget(ExtractorWidget(self, self._demo_extractor))
        layout.addWidget(self._plot_xy)
        layout.addWidget(ExtractorWidget(self, self._demo_extractor2))
        central_widget.setLayout(layout)

        self.setCentralWidget(central_widget)
        self.statusBar().show()

    def _update(self):
        while True:
            tr = self._get_transfer()
            if not tr:
                break

            self._active_data_types.add(tr.data_type_name)

            try:
                extracted = self._demo_extractor.try_extract(tr)
                if extracted:
                    self._plot_yt.add_value(self._demo_extractor, extracted.ts_mono - self._base_time, extracted.value)
            except Exception:
                self._demo_extractor.register_error()

            try:
                extracted = self._demo_extractor2.try_extract(tr)
                if extracted:
                    self._plot_xy.add_value(self._demo_extractor2, extracted.ts_mono - self._base_time, extracted.value)
            except Exception:
                self._demo_extractor2.register_error()

        self._plot_yt.update()
        self._plot_xy.update()
