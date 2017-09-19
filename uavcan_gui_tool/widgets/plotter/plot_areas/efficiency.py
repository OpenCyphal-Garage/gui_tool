#
# Copyright (C) 2016  UAVCAN Development Team  <uavcan.org>
#
# This software is distributed under the terms of the MIT License.
#
# Author: Pavel Kirienko <pavel.kirienko@zubax.com>
#

import logging
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout
from PyQt5.QtGui import QColor
from PyQt5.QtCore import Qt
from ....thirdparty.pyqtgraph import PlotWidget, mkPen
from . import AbstractPlotArea, add_crosshair
from ... import make_icon_button
from .yt import PlotAreaYTWidget

logger = logging.getLogger(__name__)


class CurveContainer:
    MAX_DATA_POINTS = 200000

    def __init__(self, plot, base_color, darkening, pen):
        logger.info("---Invoke CurveContainer init()")
        self.base_color = base_color
        self.darkening = darkening
        self.pen = pen
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

    def set_color(self, color):
        if self.base_color != color:
            self.base_color = color
            color = self.base_color.darker(self.darkening)
            logger.info('Updating color %r --> %r', self.pen.color(), color)
            self.pen.setColor(color)

    def update(self):
        self.plot.setData(self.x, self.y, pen=self.pen)


class PlotEfficientWidget(PlotAreaYTWidget):
    def __init__(self, parent, display_measurements):
        super(PlotEfficientWidget, self).__init__(parent, display_measurements)
        self.setBackgroundColor(QColor("white"))

    def setBackgroundColor(self,color):
        self._plot.setBackground(color)


class PlotThrustWidget(PlotEfficientWidget):
    def __init__(self, parent, display_measurements):
        super(PlotThrustWidget, self).__init__(parent, display_measurements)

    def setBackgroundColor(self,color):
        self._plot.setBackground(color)
