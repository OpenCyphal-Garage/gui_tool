#
# Copyright (C) 2016  UAVCAN Development Team  <uavcan.org>
#
# This software is distributed under the terms of the MIT License.
#
# Author: Pavel Kirienko <pavel.kirienko@zubax.com>
#

import logging
import numpy
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QSpinBox, QComboBox, QLabel
from PyQt5.QtGui import QColor
from PyQt5.QtCore import Qt
from pyqtgraph import PlotWidget, mkPen, mkBrush
from .abstract_plot_area import AbstractPlotArea


logger = logging.getLogger(__name__)


class CurveContainer:
    def __init__(self, plot, color):
        self.pen = mkPen(color=color, width=1)
        self.plot = plot
        self.x = []
        self.y = []

    def add_point(self, x, y, max_data_points):
        while len(self.x) >= max_data_points:
            self.x.pop(0)
            self.y.pop(0)
        assert len(self.x) == len(self.y)
        self.x.append(x)
        self.y.append(y)

    def set_color(self, color):
        if self.pen.color() != color:
            logger.info('Updating color %r --> %r', self.pen.color(), color)
            self.pen.setColor(color)

    def update(self):
        self.plot.setData(self.x, self.y, pen=self.pen)


class PlotAreaXYWidget(QWidget, AbstractPlotArea):
    def __init__(self, parent):
        super(PlotAreaXYWidget, self).__init__(parent)

        self._extractor_associations = {}       # Extractor : plot

        self._max_data_points = 100000

        self._max_data_points_spinbox = QSpinBox(self)
        self._max_data_points_spinbox.setMinimum(1)
        self._max_data_points_spinbox.setMaximum(1000000)
        self._max_data_points_spinbox.setValue(self._max_data_points)
        self._max_data_points_spinbox.valueChanged.connect(self._update_max_data_points)

        self._plot_mode_box = QComboBox(self)
        self._plot_mode_box.setEditable(False)
        self._plot_mode_box.addItems(['Line', 'Scatter'])
        self._plot_mode_box.setCurrentIndex(0)
        self._plot_mode_box.currentTextChanged.connect(self.clear)

        self._plot = PlotWidget(self, background=QColor(Qt.black))
        self._plot.showButtons()
        self._plot.enableAutoRange()
        self._plot.showGrid(x=True, y=True, alpha=0.4)

        layout = QVBoxLayout(self)
        layout.addWidget(self._plot, 1)

        controls_layout = QHBoxLayout(self)
        controls_layout.addWidget(QLabel('Data points per plot:', self))
        controls_layout.addWidget(self._max_data_points_spinbox)
        controls_layout.addWidget(QLabel('Plot style:', self))
        controls_layout.addWidget(self._plot_mode_box)
        controls_layout.addStretch(1)

        layout.addLayout(controls_layout)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

    def _update_max_data_points(self):
        self._max_data_points = self._max_data_points_spinbox.value()

    def _forge_curve(self, base_color):
        logger.info('Adding new curve')

        mode = self._plot_mode_box.currentText().lower()
        if mode == 'line':
            plot = self._plot.plot()
        elif mode == 'scatter':
            plot = self._plot.scatterPlot(symbol='+', size=3)
        else:
            raise RuntimeError('Invalid plot mode: %r' % mode)

        return CurveContainer(plot, base_color)

    def add_value(self, extractor, _timestamp, xy):
        try:
            x, y = xy
        except Exception:
            if extractor in self._extractor_associations:
                self.remove_curves_provided_by_extractor(extractor)
            raise RuntimeError('XY must be an iterable with exactly 2 elements')

        if extractor not in self._extractor_associations:
            self._extractor_associations[extractor] = self._forge_curve(extractor.color)

        self._extractor_associations[extractor].add_point(float(x), float(y), self._max_data_points)
        self._extractor_associations[extractor].set_color(extractor.color)

    def remove_curves_provided_by_extractor(self, extractor):
        self._plot.removeItem(self._extractor_associations[extractor].plot)
        del self._extractor_associations[extractor]

    def clear(self):
        for k in list(self._extractor_associations.keys()):
            self.remove_curves_provided_by_extractor(k)

    def update(self):
        for c in self._extractor_associations.values():
            c.update()
