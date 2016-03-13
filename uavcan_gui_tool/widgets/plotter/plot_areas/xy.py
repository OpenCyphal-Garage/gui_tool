#
# Copyright (C) 2016  UAVCAN Development Team  <uavcan.org>
#
# This software is distributed under the terms of the MIT License.
#
# Author: Pavel Kirienko <pavel.kirienko@zubax.com>
#

import math
import logging
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QSpinBox, QComboBox, QLabel, QCheckBox, QDoubleSpinBox
from PyQt5.QtGui import QColor
from PyQt5.QtCore import Qt
from pyqtgraph import PlotWidget, mkPen
from . import AbstractPlotArea, add_crosshair
from ... import make_icon_button


logger = logging.getLogger(__name__)


class AbstractPlotContainer:
    def __init__(self, plot):
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

    def update(self):
        self.plot.setData(self.x, self.y)


class LinePlotContainer(AbstractPlotContainer):
    def __init__(self, plot, pen):
        super(LinePlotContainer, self).__init__(plot)
        self.pen = pen

    def set_color(self, color):
        self.pen.setColor(color)
        self.plot.setPen(self.pen)


class ScatterPlotContainer(AbstractPlotContainer):
    def __init__(self, parent, color):
        self.parent = parent
        super(ScatterPlotContainer, self).__init__(self._inst(color))

    def _inst(self, color):
        return self.parent.scatterPlot(symbol='+', size=2, pen=mkPen(color=color, width=1))

    def set_color(self, color):
        # We have to re-create the plot from scratch, because seems to be impossible to re-color a ScatterPlot
        # once it has been created. Either it's bug in PyQtGraph, or I'm doing something wrong.
        self.parent.removeItem(self.plot)
        self.plot = self._inst(color)


class PlotAreaXYWidget(QWidget, AbstractPlotArea):
    def __init__(self, parent, display_measurements):
        super(PlotAreaXYWidget, self).__init__(parent)

        self._extractor_associations = {}       # Extractor : plot

        self._clear_button = make_icon_button('eraser', 'Clear all plots', self, on_clicked=self.reset)

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
        self._plot_mode_box.currentTextChanged.connect(self.reset)

        self._lock_aspect_ratio_checkbox = QCheckBox('Lock aspect ratio:', self)
        self._lock_aspect_ratio_checkbox.setChecked(True)

        self._aspect_ratio_spinbox = QDoubleSpinBox(self)
        self._aspect_ratio_spinbox.setMinimum(1e-3)
        self._aspect_ratio_spinbox.setMaximum(1e+3)
        self._aspect_ratio_spinbox.setDecimals(3)
        self._aspect_ratio_spinbox.setValue(1)
        self._aspect_ratio_spinbox.setSingleStep(0.1)

        self._lock_aspect_ratio_checkbox.clicked.connect(self._update_aspect_ratio)
        self._aspect_ratio_spinbox.valueChanged.connect(self._update_aspect_ratio)

        self._plot = PlotWidget(self, background=QColor(Qt.black))
        self._plot.showButtons()
        self._plot.enableAutoRange()
        self._plot.showGrid(x=True, y=True, alpha=0.4)

        layout = QVBoxLayout(self)
        layout.addWidget(self._plot, 1)

        controls_layout = QHBoxLayout(self)
        controls_layout.addWidget(self._clear_button)
        controls_layout.addStretch(1)
        controls_layout.addWidget(QLabel('Points per plot:', self))
        controls_layout.addWidget(self._max_data_points_spinbox)
        controls_layout.addWidget(QLabel('Style:', self))
        controls_layout.addWidget(self._plot_mode_box)
        controls_layout.addWidget(self._lock_aspect_ratio_checkbox)
        controls_layout.addWidget(self._aspect_ratio_spinbox)

        layout.addLayout(controls_layout)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

        # Crosshair
        def _render_measurements(cur, ref):
            text = 'x %.6f,  y %.6f' % cur
            if ref is None:
                return text
            dx = cur[0] - ref[0]
            dy = cur[1] - ref[1]
            dist = math.sqrt(dx ** 2 + dy ** 2)
            text += ';' + ' ' * 4 + 'dx %.6f,  dy %.6f,  dist %.6f' % (dx, dy, dist)
            display_measurements(text)

        display_measurements('Hover to sample X/Y, click to set new reference')
        add_crosshair(self._plot, _render_measurements)

        # Initialization
        self._update_aspect_ratio()
        self._update_max_data_points()

    def _update_max_data_points(self):
        self._max_data_points = self._max_data_points_spinbox.value()

    def _update_aspect_ratio(self):
        if self._lock_aspect_ratio_checkbox.isChecked():
            self._aspect_ratio_spinbox.setEnabled(True)
            self._plot.setAspectLocked(True, ratio=self._aspect_ratio_spinbox.value())
        else:
            self._aspect_ratio_spinbox.setEnabled(False)
            self._plot.setAspectLocked(False)

    def _forge_curve(self, color):
        logger.info('Adding new curve')

        mode = self._plot_mode_box.currentText().lower()
        if mode == 'line':
            return LinePlotContainer(self._plot.plot(), mkPen(color=color, width=1))
        elif mode == 'scatter':
            return ScatterPlotContainer(self._plot, color)
        else:
            raise RuntimeError('Invalid plot mode: %r' % mode)

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

    def _do_clear(self):
        for k in list(self._extractor_associations.keys()):
            self.remove_curves_provided_by_extractor(k)

    def reset(self):
        self._do_clear()
        self._plot.enableAutoRange()

    def update(self):
        for c in self._extractor_associations.values():
            c.update()
