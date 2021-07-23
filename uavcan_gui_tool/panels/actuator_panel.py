#
# Copyright (C) 2021  UAVCAN Development Team  <uavcan.org>
#
# This software is distributed under the terms of the MIT License.
#
# Author: Tom Pittenger <magicrub@gmail.com>
#

import pyuavcan_v0
from functools import partial
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout, QWidget, QLabel, QDialog, QSlider, QSpinBox, QDoubleSpinBox, QCheckBox, \
    QPlainTextEdit
from PyQt5.QtCore import QTimer, Qt
from logging import getLogger
from ..widgets import make_icon_button, get_icon, get_monospace_font

__all__ = 'PANEL_NAME', 'spawn', 'get_icon'

PANEL_NAME = 'Actuator Panel'


logger = getLogger(__name__)

_singleton = None



class PercentSlider(QWidget):
    def __init__(self, parent):
        super(PercentSlider, self).__init__(parent)

        self._slider = QSlider(Qt.Vertical, self)
        self._slider.setMinimum(-1000)
        self._slider.setMaximum(1000)
        self._slider.setValue(0)
        self._slider.setTickInterval(1000)
        self._slider.setTickPosition(QSlider.TicksBothSides)
        self._slider.valueChanged.connect(lambda: self._spinbox.setValue(self._slider.value()/1000.0))

        self._spinbox = QDoubleSpinBox(self)
        self._spinbox.setMinimum(-1)
        self._spinbox.setMaximum(1)
        self._spinbox.setValue(0)
        self._spinbox.setDecimals(3)
        self._spinbox.setSingleStep(0.001)
        self._spinbox.valueChanged.connect(lambda: self._slider.setValue(self._spinbox.value()*1000.0))

        self._zero_button = make_icon_button('hand-stop-o', 'Zero setpoint', self, text = 'Zero', on_clicked=self.zero)

        self._actuator_id = QSpinBox(self)
        self._actuator_id.setMinimum(0)
        self._actuator_id.setMaximum(15)
        self._actuator_id.setValue(0)
        self._actuator_id.setPrefix('ID: ')

        self._enabled = QCheckBox('Enabled', self)
        self._enabled.setGeometry(0, 0, 10, 10)

        layout = QVBoxLayout(self)
        sub_layout = QHBoxLayout(self)
        sub_layout.addStretch()
        sub_layout.addWidget(self._slider)
        sub_layout.addStretch()
        layout.addLayout(sub_layout)
        layout.addWidget(self._spinbox)
        layout.addWidget(self._zero_button)
        layout.addWidget(self._actuator_id)
        layout.addWidget(self._enabled)
        self.setLayout(layout)

        self.setMinimumHeight(400)

    def zero(self):
        self._slider.setValue(0)

    def get_value(self):
        return self._spinbox.value()

    def get_actuator_id(self):
        return self._actuator_id.value()

    def is_enabled(self):
        return self._enabled.isChecked()


class ActuatorPanel(QDialog):
    DEFAULT_INTERVAL = 0.1

    def __init__(self, parent, node):
        super(ActuatorPanel, self).__init__(parent)
        self.setWindowTitle('Actuator Management Panel')
        self.setAttribute(Qt.WA_DeleteOnClose)              # This is required to stop background timers!

        self._node = node

        self._sliders = [PercentSlider(self) for _ in range(4)]

        self._num_sliders = QSpinBox(self)
        self._num_sliders.setMinimum(len(self._sliders))
        self._num_sliders.setMaximum(20)
        self._num_sliders.setValue(len(self._sliders))
        self._num_sliders.valueChanged.connect(self._update_number_of_sliders)

        self._bcast_interval = QDoubleSpinBox(self)
        self._bcast_interval.setMinimum(0.01)
        self._bcast_interval.setMaximum(9.9)
        self._bcast_interval.setSingleStep(0.01)
        self._bcast_interval.setValue(self.DEFAULT_INTERVAL)
        self._bcast_interval.valueChanged.connect(
            lambda: self._bcast_timer.setInterval(self._bcast_interval.value() * 1e3))

        self._stop_all = make_icon_button('hand-stop-o', 'Zero all channels', self, text='Zero All',
                                          on_clicked=self._do_stop_all)

        self._pause = make_icon_button('pause', 'Pause publishing', self, checkable=True, text='Pause')

        self._msg_viewer = QPlainTextEdit(self)
        self._msg_viewer.setReadOnly(True)
        self._msg_viewer.setLineWrapMode(QPlainTextEdit.NoWrap)
        self._msg_viewer.setFont(get_monospace_font())
        self._msg_viewer.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._msg_viewer.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        self._bcast_timer = QTimer(self)
        self._bcast_timer.start(self.DEFAULT_INTERVAL * 1e3)
        self._bcast_timer.timeout.connect(self._do_broadcast)

        layout = QVBoxLayout(self)

        self._slider_layout = QHBoxLayout(self)
        for sl in self._sliders:
            self._slider_layout.addWidget(sl)
        layout.addLayout(self._slider_layout)

        layout.addWidget(self._stop_all)

        controls_layout = QHBoxLayout(self)
        controls_layout.addWidget(QLabel('Channels:', self))
        controls_layout.addWidget(self._num_sliders)
        controls_layout.addWidget(QLabel('Broadcast interval:', self))
        controls_layout.addWidget(self._bcast_interval)
        controls_layout.addWidget(QLabel('sec', self))
        controls_layout.addStretch()
        controls_layout.addWidget(self._pause)
        layout.addLayout(controls_layout)

        layout.addWidget(QLabel('Generated message:', self))
        layout.addWidget(self._msg_viewer)

        self.setLayout(layout)
        self.resize(self.minimumWidth(), self.minimumHeight())

    def _do_broadcast(self):
        try:
            if not self._pause.isChecked():
#                msg = pyuavcan_v0.equipment.esc.RawCommand()
                msg = pyuavcan_v0.equipment.actuator.ArrayCommand()
                for sl in self._sliders:
                    if sl.is_enabled() == False:
                        continue
                    msg_cmd = pyuavcan_v0.equipment.actuator.Command()
                    msg_cmd.actuator_id = sl.get_actuator_id()
                    msg_cmd.command_value = sl.get_value()
                    msg_cmd.command_type = 0
                    msg.commands.append(msg_cmd)

                self._node.broadcast(msg)
                self._msg_viewer.setPlainText(pyuavcan_v0.to_yaml(msg))
            else:
                self._msg_viewer.setPlainText('Paused')
        except Exception as ex:
            self._msg_viewer.setPlainText('Publishing failed:\n' + str(ex))

    def _do_stop_all(self):
        for sl in self._sliders:
            sl.zero()

    def _update_number_of_sliders(self):
        num_sliders = self._num_sliders.value()

        while len(self._sliders) > num_sliders:
            removee = self._sliders[-1]
            self._sliders = self._sliders[:-1]
            self._slider_layout.removeWidget(removee)
            removee.close()
            removee.deleteLater()

        while len(self._sliders) < num_sliders:
            new = PercentSlider(self)
            self._slider_layout.addWidget(new)
            self._sliders.append(new)

        def deferred_resize():
            self.resize(self.minimumWidth(), self.height())

        deferred_resize()
        # noinspection PyCallByClass,PyTypeChecker
        QTimer.singleShot(200, deferred_resize)

    def __del__(self):
        global _singleton
        _singleton = None

    def closeEvent(self, event):
        global _singleton
        _singleton = None
        super(ActuatorPanel, self).closeEvent(event)


def spawn(parent, node):
    global _singleton
    if _singleton is None:
        _singleton = ActuatorPanel(parent, node)

    _singleton.show()
    _singleton.raise_()
    _singleton.activateWindow()

    return _singleton


get_icon = partial(get_icon, 'asterisk')
