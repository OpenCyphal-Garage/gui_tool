#
# Copyright (C) 2016  UAVCAN Development Team  <uavcan.org>
#
# This software is distributed under the terms of the MIT License.
#
# Author: Pavel Kirienko <pavel.kirienko@zubax.com>
#

from ..widgets import show_error

# TODO: Load all inner modules automatically. This is not really easy because we have to support freezing.
from . import esc_panel
from . import actuator_panel


class PanelDescriptor:
    def __init__(self, module):
        self.name = module.PANEL_NAME
        self._module = module

    def get_icon(self):
        # noinspection PyBroadException
        try:
            return self._module.get_icon()
        except Exception:
            pass

    def safe_spawn(self, parent, node):
        try:
            return self._module.spawn(parent, node)
        except Exception as ex:
            show_error('Panel error', 'Could not spawn panel', ex)


PANELS = sorted([
    PanelDescriptor(esc_panel),
    PanelDescriptor(actuator_panel)
], key=lambda x: x.name)
