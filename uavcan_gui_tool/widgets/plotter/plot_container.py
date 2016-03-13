#
# Copyright (C) 2016  UAVCAN Development Team  <uavcan.org>
#
# This software is distributed under the terms of the MIT License.
#
# Author: Pavel Kirienko <pavel.kirienko@zubax.com>
#

import logging
from PyQt5.QtWidgets import QDockWidget, QVBoxLayout, QHBoxLayout, QWidget
from .. import make_icon_button
from .value_extractor_views import NewValueExtractorWindow, ExtractorWidget


logger = logging.getLogger(__name__)


class PlotContainerWidget(QDockWidget):
    def __init__(self, parent, plot_area_class, active_data_types):
        super(PlotContainerWidget, self).__init__(parent)

        self._plot_area = plot_area_class(self)
        self.update = self._plot_area.update

        self._active_data_types = active_data_types
        self._extractors = []

        self._new_extractor_button = make_icon_button('plus', 'Add new plot', self, text='New extractor...',
                                                      on_clicked=self._do_new_extractor)

        widget = QWidget(self)

        layout = QVBoxLayout(widget)
        layout.addWidget(self._plot_area, 1)

        self._extractors_layout = QVBoxLayout(widget)
        self._extractors_layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(self._extractors_layout)

        controls_layout = QHBoxLayout(widget)
        controls_layout.addWidget(self._new_extractor_button)
        controls_layout.addStretch(1)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(controls_layout)
        widget.setLayout(layout)

        self.setWidget(widget)
        self.setFeatures(QDockWidget.DockWidgetFloatable |
                         QDockWidget.DockWidgetClosable |
                         QDockWidget.DockWidgetMovable)

    def _do_new_extractor(self):
        def done(extractor):
            self._extractors.append(extractor)
            widget = ExtractorWidget(self, extractor)
            self._extractors_layout.addWidget(widget)

            def remove():
                self._plot_area.remove_curves_provided_by_extractor(extractor)
                self._extractors.remove(extractor)
                self._extractors_layout.removeWidget(widget)

            widget.on_remove = remove

        win = NewValueExtractorWindow(self, self._active_data_types)
        win.on_done = done
        win.show()

    def process_transfer(self, timestamp, tr):
        for extractor in self._extractors:
            try:
                value = extractor.try_extract(tr)
                if value is None:
                    continue
                self._plot_area.add_value(extractor, timestamp, value)
            except Exception:
                extractor.register_error()
