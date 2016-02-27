#
# Copyright (C) 2016  UAVCAN Development Team  <uavcan.org>
#
# This software is distributed under the terms of the MIT License.
#
# Author: Pavel Kirienko <pavel.kirienko@zubax.com>
#

import uavcan
from PyQt5.QtWidgets import QGroupBox, QVBoxLayout, QHBoxLayout
from logging import getLogger
from . import BasicTable, flash


logger = getLogger(__name__)


class FileServerWidget(QGroupBox):
    def __init__(self, parent, node):
        super(FileServerWidget, self).__init__(parent)
        self.setTitle('File server (uavcan.protocol.file.*)')

        self._node = node



