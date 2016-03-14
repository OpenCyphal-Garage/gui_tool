#
# Copyright (C) 2016  UAVCAN Development Team  <uavcan.org>
#
# This software is distributed under the terms of the MIT License.
#
# Author: Pavel Kirienko <pavel.kirienko@zubax.com>
#

import time
import logging
from functools import partial
from PyQt5.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QAction
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QKeySequence
from .. import get_app_icon, get_icon
from .plot_areas import PLOT_AREAS
from .plot_container import PlotContainerWidget


logger = logging.getLogger(__name__)


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

        self._plot_containers = []

        #
        # Control menu
        #
        control_menu = self.menuBar().addMenu('&Control')

        self._stop_action = QAction(get_icon('stop'), '&Stop Updates', self)
        self._stop_action.setStatusTip('While stopped, all new data will be discarded')
        self._stop_action.setShortcut(QKeySequence('Ctrl+Shift+S'))
        self._stop_action.setCheckable(True)
        self._stop_action.toggled.connect(self._on_stop_toggled)
        control_menu.addAction(self._stop_action)

        self._pause_action = QAction(get_icon('pause'), '&Pause Updates', self)
        self._pause_action.setStatusTip('While paused, new data will be accumulated in memory '
                                        'to be processed once un-paused')
        self._pause_action.setShortcut(QKeySequence('Ctrl+Shift+P'))
        self._pause_action.setCheckable(True)
        self._pause_action.toggled.connect(self._on_pause_toggled)
        control_menu.addAction(self._pause_action)

        control_menu.addSeparator()

        self._reset_time_action = QAction(get_icon('history'), '&Reset', self)
        self._reset_time_action.setStatusTip('Base time will be reset; all plots will be reset')
        self._reset_time_action.setShortcut(QKeySequence('Ctrl+Shift+R'))
        self._reset_time_action.triggered.connect(self._do_reset)
        control_menu.addAction(self._reset_time_action)

        #
        # New Plot menu
        #
        plot_menu = self.menuBar().addMenu('&New Plot')
        for idx, pl_name in enumerate(PLOT_AREAS.keys()):
            new_plot_action = QAction('Add ' + pl_name, self)
            new_plot_action.setStatusTip('Add new plot window')
            new_plot_action.setShortcut(QKeySequence('Ctrl+Alt+' + str(idx)))
            new_plot_action.triggered.connect(partial(self._do_add_new_plot, pl_name))
            plot_menu.addAction(new_plot_action)

        #
        # Window stuff
        #
        self.statusBar().showMessage('Use the "New Plot" menu to add plots')
        self.setCentralWidget(None)

        self.resize(800, 600)

    def _on_stop_toggled(self, checked):
        self._pause_action.setChecked(False)
        self.statusBar().showMessage('Stopped' if checked else 'Un-stopped')

    def _on_pause_toggled(self, checked):
        self.statusBar().showMessage('Paused' if checked else 'Un-paused')

    def _do_add_new_plot(self, plot_area_name):
        def remove():
            self._plot_containers.remove(plc)

        plc = PlotContainerWidget(self, PLOT_AREAS[plot_area_name], self._active_data_types)
        plc.on_close = remove
        self._plot_containers.append(plc)

        docks = [
            Qt.LeftDockWidgetArea,
            Qt.LeftDockWidgetArea,
            Qt.RightDockWidgetArea,
            Qt.RightDockWidgetArea,
        ]
        dock_to = docks[(len(self._plot_containers) - 1) % len(docks)]
        self.addDockWidget(dock_to, plc)

    def _do_reset(self):
        self._base_time = time.monotonic()

        for plc in self._plot_containers:
            try:
                plc.reset()
            except Exception:
                logger.error('Failed to reset plot container', exc_info=True)

        logger.info('Reset done, new time base %r', self._base_time)

    def _update(self):
        if self._stop_action.isChecked():
            while self._get_transfer() is not None:     # Discarding everything
                pass
            return

        if not self._pause_action.isChecked():
            while True:
                tr = self._get_transfer()
                if not tr:
                    break

                self._active_data_types.add(tr.data_type_name)

                for plc in self._plot_containers:
                    try:
                        plc.process_transfer(tr.ts_mono - self._base_time, tr)
                    except Exception:
                        logger.error('Plot container failed to process a transfer', exc_info=True)

        for plc in self._plot_containers:
            try:
                plc.update()
            except Exception:
                logger.error('Plot container failed to update', exc_info=True)
