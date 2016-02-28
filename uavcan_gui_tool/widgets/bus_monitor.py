#
# Copyright (C) 2016  UAVCAN Development Team  <uavcan.org>
#
# This software is distributed under the terms of the MIT License.
#
# Author: Pavel Kirienko <pavel.kirienko@zubax.com>
#

import datetime
import time
import os
import uavcan
from PyQt5.QtWidgets import QGroupBox, QVBoxLayout, QHBoxLayout, QHeaderView, QLabel, QGridLayout, QSizePolicy
from PyQt5.QtGui import QColor, QIcon
from PyQt5.QtCore import Qt, QTimer
from pyqtgraph import PlotWidget, mkPen
from logging import getLogger
from . import BasicTable, map_7bit_to_color, RealtimeLogWidget, get_monospace_font, get_icon, flash


logger = getLogger(__name__)


def parse_can_frame(frame):
    if frame.extended:
        can_id = frame.id
        source_node_id = can_id & 0x7F

        service_not_message = bool((can_id >> 7) & 1)
        if service_not_message:
            destination_node_id = (can_id >> 8) & 0x7F
            request_not_response = bool((can_id >> 15) & 1)
            service_type_id = (can_id >> 16) & 0xFF
            try:
                data_type_name = uavcan.DATATYPES[(service_type_id, uavcan.dsdl.CompoundType.KIND_SERVICE)].full_name
            except KeyError:
                data_type_name = '<unknown service %d>' % service_type_id
        else:
            message_type_id = (can_id >> 8) & 0xFFFF
            if source_node_id == 0:
                source_node_id = 'Anon'
                message_type_id &= 0b11
            destination_node_id = ''
            try:
                data_type_name = uavcan.DATATYPES[(message_type_id, uavcan.dsdl.CompoundType.KIND_MESSAGE)].full_name
            except KeyError:
                data_type_name = '<unknown message %d>' % message_type_id
    else:
        data_type_name = 'N/A'
        source_node_id = 'N/A'
        destination_node_id = 'N/A'

    return {
        'data_type': data_type_name,
        'src': source_node_id,
        'dst': destination_node_id,
    }


def render_node_id_with_color(frame, field):
    nid = parse_can_frame(frame)[field]
    return nid, (map_7bit_to_color(nid) if isinstance(nid, int) else None)


def render_data_type_with_color(frame):
    dtname = parse_can_frame(frame)['data_type']
    color_hash = sum(dtname.encode('ascii')) & 0xF7
    return dtname, map_7bit_to_color(color_hash)


def colorize_can_id(frame):
    if not frame.extended:
        return
    mask = 0b11111
    priority = (frame.id >> 24) & mask
    col = QColor()
    col.setRgb(0xFF, 0xFF - (mask - priority) * 6, 0xFF)
    return col


def colorize_transfer_id(e):
    if len(e[1].data) < 1:
        return

    # Making a rather haphazard hash using transfer ID and a part of CAN ID
    x = (e[1].data[-1] & 0b11111) | (((e[1].id >> 16) & 0b1111) << 5)
    red = ((x >> 6) & 0b111) * 25
    green = ((x >> 3) & 0b111) * 25
    blue = (x & 0b111) * 25

    col = QColor()
    col.setRgb(0xFF - red, 0xFF - green, 0xFF - blue)
    return col


class TimestampRenderer:
    FORMAT = '%H:%M:%S.%f'

    def __init__(self):
        self._prev_ts = 0

    def __call__(self, e):
        ts = datetime.datetime.fromtimestamp(e[1].ts_real).strftime(self.FORMAT)
        col = QColor()

        # Constraining delta to [0, 1]
        delta = min(1, e[1].ts_real - self._prev_ts)
        if delta < 0:
            col.setRgb(255, 230, 230)
        else:
            self._prev_ts = e[1].ts_real
            col.setRgb(*([255 - int(192 * delta)] * 3))
        return ts, col

    @staticmethod
    def parse_timestamp(ts):
        return datetime.datetime.strptime(ts, TimestampRenderer.FORMAT).timestamp()


class TrafficStatCounter:
    MOVING_AVERAGE_LENGTH = 4
    FPS_ESTIMATION_WINDOW = 0.5

    def __init__(self):
        self._rx = 0
        self._tx = 0
        self._fps = 0
        self._prev_fps_checkpoint_mono = 0
        self._frames_since_fps_checkpoint = 0
        self._last_fps_estimates = [0] * self.MOVING_AVERAGE_LENGTH

    def add_frame(self, direction, frame):
        if direction == 'tx':
            self._tx += 1
        else:
            self._rx += 1

        # Updating FPS estimate.
        # It is extremely important that the algorithm relies only on the timestamps provided by the driver!
        # Naive timestamping produces highly unreliable estimates, because the application is not nearly real-time.
        self._frames_since_fps_checkpoint += 1
        if direction == 'rx':
            dt = frame.ts_monotonic - self._prev_fps_checkpoint_mono
            if dt >= self.FPS_ESTIMATION_WINDOW:
                self._last_fps_estimates.pop()
                self._last_fps_estimates.insert(0, self._frames_since_fps_checkpoint / dt)
                self._prev_fps_checkpoint_mono = frame.ts_monotonic
                self._frames_since_fps_checkpoint = 0

    @property
    def rx(self):
        return self._rx

    @property
    def tx(self):
        return self._tx

    @property
    def total(self):
        return self._rx + self._tx

    def get_frames_per_second(self):
        return (sum(self._last_fps_estimates) / len(self._last_fps_estimates)), self._prev_fps_checkpoint_mono


class BusMonitorWidget(QGroupBox):
    DEFAULT_PLOT_X_RANGE = 120
    BUS_LOAD_PLOT_MAX_SAMPLES = 5000

    def __init__(self, parent, node, iface_name):
        super(BusMonitorWidget, self).__init__(parent)
        self.setTitle('CAN bus activity (%s)' % iface_name.split(os.path.sep)[-1])

        self._node = node
        self._hook_handle = self._node.can_driver.add_io_hook(self._frame_hook)

        self._columns = [
            BasicTable.Column('Dir',
                              lambda e: (e[0].upper()),
                              searchable=False),
            BasicTable.Column('Local Time', TimestampRenderer(), searchable=False),
            BasicTable.Column('CAN ID',
                              lambda e: (('%0*X' % (8 if e[1].extended else 3, e[1].id)).rjust(8),
                                         colorize_can_id(e[1]))),
            BasicTable.Column('Data Hex',
                              lambda e: (' '.join(['%02X' % x for x in e[1].data]).ljust(3 * e[1].MAX_DATA_LENGTH),
                                         colorize_transfer_id(e))),
            BasicTable.Column('Data ASCII',
                              lambda e: (''.join([(chr(x) if 32 <= x <= 126 else '.') for x in e[1].data]),
                                         colorize_transfer_id(e))),
            BasicTable.Column('Src',
                              lambda e: render_node_id_with_color(e[1], 'src')),
            BasicTable.Column('Dst',
                              lambda e: render_node_id_with_color(e[1], 'dst')),
            BasicTable.Column('Data Type',
                              lambda e: render_data_type_with_color(e[1]),
                              resize_mode=QHeaderView.Stretch),
        ]

        self._log_widget = RealtimeLogWidget(self, columns=self._columns, font=get_monospace_font(small=True),
                                             post_redraw_hook=self._redraw_hook)
        self._log_widget.on_selection_changed = self._update_measurement_display

        def flip_row_mark(row, col):
            if col == 0:
                item = self._log_widget.table.item(row, col)
                if item.icon().isNull():
                    item.setIcon(get_icon('circle'))
                    flash(self, 'Row %d was marked, click again to unmark', row, duration=3)
                else:
                    item.setIcon(QIcon())

        self._log_widget.table.cellPressed.connect(flip_row_mark)

        self._stat_update_timer = QTimer(self)
        self._stat_update_timer.setSingleShot(False)
        self._stat_update_timer.timeout.connect(self._update_stat)
        self._stat_update_timer.start(500)

        self._traffic_stat = TrafficStatCounter()

        self._stat_frames_tx = QLabel('N/A', self)
        self._stat_frames_rx = QLabel('N/A', self)
        self._stat_traffic = QLabel('N/A', self)

        self._load_plot = PlotWidget(background=(0, 0, 0))
        self._load_plot.setRange(xRange=(0, self.DEFAULT_PLOT_X_RANGE), padding=0)
        self._load_plot.setMaximumHeight(150)
        self._load_plot.setMinimumHeight(100)
        self._load_plot.setMinimumWidth(100)
        self._load_plot.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)
        self._load_plot.showGrid(x=True, y=True, alpha=0.4)
        self._load_plot.setToolTip('Frames per second')
        self._load_plot.getPlotItem().getViewBox().setMouseEnabled(x=True, y=False)
        self._load_plot.enableAutoRange()
        self._bus_load_plot = self._load_plot.plot(name='Frames per second', pen=mkPen(QColor(Qt.lightGray), width=1))
        self._bus_load_samples = [], []
        self._started_at_mono = time.monotonic()

        layout = QVBoxLayout(self)

        layout.addWidget(self._log_widget, 1)

        stat_vars_layout = QGridLayout(self)
        stat_layout_next_row = 0

        def add_stat_row(label, value):
            nonlocal stat_layout_next_row
            stat_vars_layout.addWidget(QLabel(label, self), stat_layout_next_row, 0)
            stat_vars_layout.addWidget(value, stat_layout_next_row, 1)
            value.setMinimumWidth(75)
            stat_layout_next_row += 1

        add_stat_row('Frames transmitted:', self._stat_frames_tx)
        add_stat_row('Frames received:', self._stat_frames_rx)
        add_stat_row('Frames per second:', self._stat_traffic)
        stat_vars_layout.setRowStretch(stat_layout_next_row, 1)

        stat_layout = QHBoxLayout(self)
        stat_layout.addLayout(stat_vars_layout)
        stat_layout.addWidget(self._load_plot, 1)

        layout.addLayout(stat_layout, 0)
        self.setLayout(layout)

    def close(self):
        self._hook_handle.remove()

    def _update_stat(self):
        bus_load, ts_mono = self._traffic_stat.get_frames_per_second()
        self._stat_traffic.setText(str(int(bus_load + 0.5)))

        if len(self._bus_load_samples[0]) >= self.BUS_LOAD_PLOT_MAX_SAMPLES:
            self._bus_load_samples[0].pop(0)
            self._bus_load_samples[1].pop(0)

        self._bus_load_samples[1].append(bus_load)
        self._bus_load_samples[0].append(ts_mono - self._started_at_mono)

        self._bus_load_plot.setData(*self._bus_load_samples)

        (xmin, xmax), _ = self._load_plot.viewRange()
        diff = xmax - xmin
        xmax = self._bus_load_samples[0][-1]
        xmin = self._bus_load_samples[0][-1] - diff
        self._load_plot.setRange(xRange=(xmin, xmax), padding=0)

    def _redraw_hook(self):
        self._stat_frames_tx.setText(str(self._traffic_stat.tx))
        self._stat_frames_rx.setText(str(self._traffic_stat.rx))

    def _frame_hook(self, direction, frame):
        self._traffic_stat.add_frame(direction, frame)
        self._log_widget.add_item_async((direction, frame))

    def _update_measurement_display(self, selected_rows_cols):
        if not selected_rows_cols:
            return

        min_row = min([row for row, _ in selected_rows_cols])
        max_row = max([row for row, _ in selected_rows_cols])

        def get_row_ts(row):
            return TimestampRenderer.parse_timestamp(self._log_widget.table.item(row, 1).text())

        def get_load_str(num_frames, dt):
            if dt >= 1e-6:
                return 'average load %.1f FPS' % (num_frames / dt)
            return 'average load is unknown'

        if min_row == max_row:
            num_frames = min_row
            first_ts = get_row_ts(0)
            current_ts = get_row_ts(min_row)
            dt = current_ts - first_ts
            flash(self, '%d frames from beginning, %.3f sec since first frame, %s',
                  num_frames, dt, get_load_str(num_frames, dt))
        else:
            num_frames = max_row - min_row + 1
            first_ts = get_row_ts(min_row)
            last_ts = get_row_ts(max_row)
            dt = last_ts - first_ts
            flash(self, '%d frames, timedelta %.6f sec, %s',
                  num_frames, dt, get_load_str(num_frames, dt))
