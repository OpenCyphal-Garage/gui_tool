#
# Copyright (C) 2016  UAVCAN Development Team  <uavcan.org>
#
# This software is distributed under the terms of the MIT License.
#
# Author: Pavel Kirienko <pavel.kirienko@zubax.com>
#

from collections import OrderedDict
from PyQt5.QtGui import QColor
from PyQt5.QtCore import Qt
from pyqtgraph import mkPen, InfiniteLine


class AbstractPlotArea:
    def add_value(self, extractor, timestamp, value):
        pass

    def remove_curves_provided_by_extractor(self, extractor):
        pass

    def update(self):
        pass

    def reset(self):
        pass


def add_crosshair(plot, render_measurements, color=Qt.gray):
    pen = mkPen(color=QColor(color), width=1)
    vline = InfiniteLine(angle=90, movable=False, pen=pen)
    hline = InfiniteLine(angle=0, movable=False, pen=pen)

    plot.addItem(vline, ignoreBounds=True)
    plot.addItem(hline, ignoreBounds=True)

    current_coordinates = None
    reference_coordinates = None

    def do_render():
        render_measurements(current_coordinates, reference_coordinates)

    def update(pos):
        nonlocal current_coordinates
        if plot.sceneBoundingRect().contains(pos):
            mouse_point = plot.getViewBox().mapSceneToView(pos)
            current_coordinates = mouse_point.x(), mouse_point.y()
            vline.setPos(mouse_point.x())
            hline.setPos(mouse_point.y())
            do_render()

    def set_reference(ev):
        nonlocal reference_coordinates
        if ev.button() == Qt.LeftButton and current_coordinates is not None:
            reference_coordinates = current_coordinates
            do_render()

    plot.scene().sigMouseMoved.connect(update)
    plot.scene().sigMouseClicked.connect(set_reference)


from .yt import PlotAreaYTWidget
from .xy import PlotAreaXYWidget

PLOT_AREAS = OrderedDict([
    ('Y-T plot', PlotAreaYTWidget),
    ('X-Y plot', PlotAreaXYWidget),
])
