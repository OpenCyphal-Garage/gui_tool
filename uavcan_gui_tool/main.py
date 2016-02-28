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

from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout
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

        self._node_spin_timer.start(1)

        self._node_monitor_widget = NodeMonitorWidget(self, node)
        self._local_node_widget = LocalNodeWidget(self, node)
        self._log_message_widget = LogMessageDisplayWidget(self, node)
        self._bus_monitor_widget = BusMonitorWidget(self, node, iface_name)
        self._dynamic_node_id_allocation_widget = DynamicNodeIDAllocatorWidget(self, node,
                                                                               self._node_monitor_widget.monitor)
        self._file_server_widget = FileServerWidget(self, node)

        outer_hbox = QHBoxLayout(self)

        left_vbox = QVBoxLayout(self)
        left_vbox.addWidget(self._local_node_widget)
        left_vbox.addWidget(self._node_monitor_widget)
        left_vbox.addWidget(self._log_message_widget)
        left_vbox.addWidget(self._file_server_widget)

        right_vbox = QVBoxLayout(self)
        right_vbox.addWidget(self._bus_monitor_widget, 1)
        right_vbox.addWidget(self._dynamic_node_id_allocation_widget)

        outer_hbox.addLayout(left_vbox, 1)
        outer_hbox.addLayout(right_vbox, 1)

        outer_widget = QWidget(self)
        outer_widget.setLayout(outer_hbox)
        self.setCentralWidget(outer_widget)

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

    exit(app.exec_())


if __name__ == '__main__':
    main()
