#
# Copyright (C) 2016  UAVCAN Development Team  <uavcan.org>
#
# This software is distributed under the terms of the MIT License.
#
# Author: Pavel Kirienko <pavel.kirienko@zubax.com>
#

import uavcan
from PyQt5.QtWidgets import QDialog
from logging import getLogger


logger = getLogger(__name__)


class NodePropertiesWindow(QDialog):
    def __init__(self, parent, node, target_node_id, file_server_widget):
        super(NodePropertiesWindow, self).__init__(parent)

        self.target_node_id = target_node_id

        self._node = node
        self._file_server_widget = file_server_widget
