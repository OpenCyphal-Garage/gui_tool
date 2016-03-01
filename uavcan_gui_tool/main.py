#!/usr/bin/env python3
#
# Copyright (C) 2016  UAVCAN Development Team  <uavcan.org>
#
# This software is distributed under the terms of the MIT License.
#
# Author: Pavel Kirienko <pavel.kirienko@zubax.com>
#

# Initializing logging first
import logging
import sys
import os

assert sys.version[0] == '3'

logging.basicConfig(stream=sys.stderr, level=logging.INFO,
                    format='%(asctime)s %(levelname)-8s %(name)-25s %(message)s')

logger = logging.getLogger(__name__)

for path in ('pyqtgraph', 'pyuavcan'):
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), path))

# Importing other stuff once the logging has been configured
import uavcan

from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter
from PyQt5.QtGui import QIcon
from PyQt5.QtCore import QTimer, Qt

from iface_configurator import run_iface_config_window
from widgets import show_error
from widgets.node_monitor import NodeMonitorWidget
from widgets.local_node import LocalNodeWidget
from widgets.log_message_display import LogMessageDisplayWidget
from widgets.bus_monitor import BusMonitorWidget
from widgets.dynamic_node_id_allocator import DynamicNodeIDAllocatorWidget
from widgets.file_server import FileServerWidget


NODE_NAME = 'org.uavcan.gui_tool'


class MainWindow(QMainWindow):
    def __init__(self, icon, node, iface_name):
        # Parent
        super(MainWindow, self).__init__()
        self.setWindowTitle('UAVCAN GUI Tool')
        self.setWindowIcon(icon)

        self._icon = icon
        self._node = node

        self._node_spin_timer = QTimer(self)
        self._node_spin_timer.timeout.connect(self._spin_node)
        self._node_spin_timer.setSingleShot(False)
        self._node_spin_timer.start(10)

        self._node_monitor_widget = NodeMonitorWidget(self, node)
        self._local_node_widget = LocalNodeWidget(self, node)
        self._log_message_widget = LogMessageDisplayWidget(self, node)
        self._bus_monitor_widget = BusMonitorWidget(self, node, iface_name)
        self._dynamic_node_id_allocation_widget = DynamicNodeIDAllocatorWidget(self, node,
                                                                               self._node_monitor_widget.monitor)
        self._file_server_widget = FileServerWidget(self, node)

        def make_vbox(*widgets, stretch_index=None):
            box = QVBoxLayout(self)
            for idx, w in enumerate(widgets):
                box.addWidget(w, 1 if idx == stretch_index else 0)
            container = QWidget(self)
            container.setLayout(box)
            return container

        def make_splitter(orientation, *widgets, stretch_index=None):
            spl = QSplitter(orientation, self)
            for w in widgets:
                spl.addWidget(w)
            if stretch_index is not None:
                spl.setStretchFactor(stretch_index, 1)
            else:
                for x in range(len(widgets)):
                    spl.setStretchFactor(x, 1)
            return spl

        self.setCentralWidget(make_splitter(Qt.Horizontal,
                                            make_splitter(Qt.Vertical,
                                                          make_vbox(self._local_node_widget,
                                                                    self._node_monitor_widget,
                                                                    stretch_index=1),
                                                          make_vbox(self._log_message_widget,
                                                                    self._file_server_widget,
                                                                    stretch_index=0)),
                                            make_splitter(Qt.Vertical,
                                                          self._bus_monitor_widget,
                                                          self._dynamic_node_id_allocation_widget,
                                                          stretch_index=0)))

    def _spin_node(self):
        # We're running the node in the GUI thread.
        # This is not great, but at the moment seems like other options are even worse.
        try:
            self._node.spin(0)
        except Exception as ex:
            logger.error('Node spin error: %r', ex, exc_info=True)


def main():
    app = QApplication(sys.argv)

    # noinspection PyBroadException
    try:
        app_icon = QIcon(os.path.join(os.path.dirname(__file__), 'icon.png'))
    except Exception:
        logger.error('Could not load icon', exc_info=True)
        app_icon = QIcon()

    while True:
        # Asking the user to specify which interface to work with
        try:
            iface, iface_kwargs = run_iface_config_window(app_icon)
            if not iface:
                exit(0)
        except Exception as ex:
            show_error('Fatal error', 'Could not list available interfaces', ex)
            exit(1)

        # Trying to start the node on the specified interface
        try:
            node_info = uavcan.protocol.GetNodeInfo.Response()
            node_info.name = NODE_NAME
            node_info.software_version.major = 1   # TODO: share with setup.py
            node_info.software_version.minor = 0

            node = uavcan.make_node(iface,
                                    node_info=node_info,
                                    mode=uavcan.protocol.NodeStatus().MODE_OPERATIONAL,
                                    **iface_kwargs)

            # Making sure the interface is alright
            node.spin(0.1)
        except Exception as ex:
            show_error('Fatal error', 'Could not initialize UAVCAN node', ex)
        else:
            break

    window = MainWindow(app_icon, node, iface)
    window.show()

    exit_code = app.exec_()

    node.close()

    exit(exit_code)


if __name__ == '__main__':
    main()
