#
# Copyright (C) 2016  UAVCAN Development Team  <uavcan.org>
#
# This software is distributed under the terms of the MIT License.
#
# Author: Pavel Kirienko <pavel.kirienko@zubax.com>
#

import logging
import numpy
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout
from PyQt5.QtGui import QColor
from PyQt5.QtCore import Qt
from pyqtgraph import PlotWidget, mkPen
from .abstract_plot_area import AbstractPlotArea
from .. import make_icon_button


logger = logging.getLogger(__name__)


class CurveContainer:
    MAX_DATA_POINTS = 200000

    def __init__(self, plot):
        self.plot = plot
        self.x = []
        self.y = []

    def add_point(self, x, y):
        while len(self.x) >= self.MAX_DATA_POINTS:
            self.x.pop(0)
            self.y.pop(0)
        assert len(self.x) == len(self.y)
        self.x.append(x)
        self.y.append(y)

    def update(self):
        self.plot.setData(self.x, self.y)


class PlotAreaYTWidget(QWidget, AbstractPlotArea):
    INITIAL_X_RANGE = 120
    MAX_CURVES_PER_EXTRACTOR = 4

    def __init__(self, parent):
        super(PlotAreaYTWidget, self).__init__(parent)

        self._extractor_associations = {}       # Extractor : plots
        self._max_x = 0

        self._autoscroll_checkbox = make_icon_button('angle-double-right',
                                                     'Scroll the plot automatically as new data arrives', self,
                                                     checkable=True, checked=True, text='Autoscroll')

        self._plot = PlotWidget(self, background=QColor(Qt.black))
        self._plot.showButtons()
        self._plot.enableAutoRange()
        self._plot.showGrid(x=True, y=True, alpha=0.4)
        self._legend = None
        # noinspection PyArgumentList
        self._plot.setRange(xRange=(0, self.INITIAL_X_RANGE), padding=0)

        layout = QVBoxLayout(self)
        layout.addWidget(self._plot, 1)
        controls_layout = QHBoxLayout(self)
        controls_layout.addWidget(self._autoscroll_checkbox)
        controls_layout.addStretch(1)
        layout.addLayout(controls_layout)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

    def _forge_curves(self, how_many, base_color):
        # Adding legend if we have more than 1 plot per extractor
        if how_many > 1 and self._legend is None:
            self._legend = self._plot.addLegend()

        out = []
        for idx in range(how_many):
            logger.info('Adding new curve')
            pen = mkPen(base_color, width=1)
            plot = self._plot.plot(name=str(idx), pen=pen)
            out.append(CurveContainer(plot))
            base_color = base_color.darker(300)

        return out

    def add_value(self, extractor, x, y):
        try:
            num_curves = len(y)
        except Exception:
            num_curves = 1
            y = y,          # do you love Python as I do

        # If number of curves changed, removing all plots from this extractor
        if extractor in self._extractor_associations and num_curves != len(self._extractor_associations[extractor]):
            self.remove_curves_provided_by_extractor(extractor)

        # Creating curves if needed
        if extractor not in self._extractor_associations:
            # Techincally, we can plot as many curves as you want, but large number may indicate that smth is wrong
            if num_curves > self.MAX_CURVES_PER_EXTRACTOR:
                raise RuntimeError('%r curves is much too many' % num_curves)
            self._extractor_associations[extractor] = self._forge_curves(num_curves, extractor.color)

        # Actually plotting
        for idx, curve in enumerate(self._extractor_associations[extractor]):
            curve.add_point(x, float(y[idx]))

        # Updating the rightmost value
        self._max_x = max(self._max_x, x)

    def remove_curves_provided_by_extractor(self, extractor):
        curves = self._extractor_associations[extractor]
        del self._extractor_associations[extractor]
        for c in curves:
            self._plot.removeItem(c.plot)

        if self._legend is not None:
            self._legend.scene().removeItem(self._legend)

    def clear(self):
        for k in list(self._extractor_associations.keys()):
            self.remove_curves_provided_by_extractor(k)

    def update(self):
        # Updating curves
        for curves in self._extractor_associations.values():
            for c in curves:
                c.update()

        # Updating view range
        if self._autoscroll_checkbox.isChecked():
            (xmin, xmax), _ = self._plot.viewRange()
            diff = xmax - xmin
            xmax = self._max_x
            xmin = self._max_x - diff
            # noinspection PyArgumentList
            self._plot.setRange(xRange=(xmin, xmax), padding=0)
