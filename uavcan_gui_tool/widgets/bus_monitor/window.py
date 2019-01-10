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
from functools import partial
import uavcan
from uavcan.driver import CANFrame
from PyQt5.QtWidgets import QMainWindow, QHeaderView, QLabel, QSplitter, QSizePolicy, QWidget, QHBoxLayout, \
    QPlainTextEdit, QDialog, QVBoxLayout, QMenu, QAction
from PyQt5.QtGui import QColor, QIcon, QTextOption
from PyQt5.QtCore import Qt, QTimer
from ...thirdparty.pyqtgraph import PlotWidget, mkPen
from logging import getLogger
from .. import BasicTable, map_7bit_to_color, RealtimeLogWidget, get_monospace_font, get_icon, flash, get_app_icon, \
    show_error
from .transfer_decoder import decode_transfer_from_frame


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
    def compute_timestamp_difference(earlier, later):
        def s2delta(string):
            h, m, s = [float(x) for x in string.split(':')]
            return datetime.timedelta(hours=h, minutes=m, seconds=s)
        return (s2delta(later) - s2delta(earlier)).total_seconds()


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


COLUMNS = [
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


def row_to_frame(table, row_index):
    if row_index >= table.rowCount():
        return None

    can_id = None
    payload = None
    extended = None

    for col_index, col_spec in enumerate(COLUMNS):
        item = table.item(row_index, col_index).text()
        if col_spec.name == 'CAN ID':
            extended = len(item.strip()) > 3
            can_id = int(item, 16)
        if col_spec.name == 'Data Hex':
            payload = bytes([int(x, 16) for x in item.split()])

    assert all(map(lambda x: x is not None, [can_id, payload, extended]))
    return CANFrame(can_id, payload, extended, ts_monotonic=-1, ts_real=-1)


class BusMonitorWindow(QMainWindow):
    DEFAULT_PLOT_X_RANGE = 120
    BUS_LOAD_PLOT_MAX_SAMPLES = 50000

    def __init__(self, get_frame, iface_name):
        super(BusMonitorWindow, self).__init__()
        self.setWindowTitle('CAN bus monitor (%s)' % iface_name.split(os.path.sep)[-1])
        self.setWindowIcon(get_app_icon())

        # get dsdl_directory from parent process, if set
        dsdl_directory = os.environ.get('UAVCAN_CUSTOM_DSDL_PATH',None)
        if dsdl_directory:
            uavcan.load_dsdl(dsdl_directory)

        self._get_frame = get_frame

        self._log_widget = RealtimeLogWidget(self, columns=COLUMNS, font=get_monospace_font(),
                                             pre_redraw_hook=self._redraw_hook)
        self._log_widget.on_selection_changed = self._update_measurement_display

        self._log_widget.table.cellClicked.connect(lambda row, col: self._decode_transfer_at_row(row))

        self._log_widget.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self._log_widget.table.customContextMenuRequested.connect(self._context_menu_requested)

        self._stat_display = QLabel('0 / 0 / 0', self)
        stat_display_label = QLabel('TX / RX / FPS: ', self)
        stat_display_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._log_widget.custom_area_layout.addWidget(stat_display_label)
        self._log_widget.custom_area_layout.addWidget(self._stat_display)

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

        self._decoded_message_box = QPlainTextEdit(self)
        self._decoded_message_box.setReadOnly(True)
        self._decoded_message_box.setFont(get_monospace_font())
        self._decoded_message_box.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._decoded_message_box.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._decoded_message_box.setPlainText('Click on a row to see decoded transfer')
        self._decoded_message_box.setLineWrapMode(QPlainTextEdit.NoWrap)
        self._decoded_message_box.setWordWrapMode(QTextOption.NoWrap)

        self._load_plot = PlotWidget(background=(0, 0, 0))
        self._load_plot.setRange(xRange=(0, self.DEFAULT_PLOT_X_RANGE), padding=0)
        self._load_plot.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)
        self._load_plot.showGrid(x=True, y=True, alpha=0.4)
        self._load_plot.setToolTip('Frames per second')
        self._load_plot.getPlotItem().getViewBox().setMouseEnabled(x=True, y=False)
        self._load_plot.enableAutoRange()
        self._bus_load_plot = self._load_plot.plot(name='Frames per second', pen=mkPen(QColor(Qt.lightGray), width=1))
        self._bus_load_samples = [], []
        self._started_at_mono = time.monotonic()

        self._footer_splitter = QSplitter(Qt.Horizontal, self)
        self._footer_splitter.addWidget(self._decoded_message_box)
        self._decoded_message_box.setMinimumWidth(400)
        self._footer_splitter.addWidget(self._load_plot)
        self._load_plot.setMinimumWidth(200)

        splitter = QSplitter(Qt.Vertical, self)
        splitter.addWidget(self._log_widget)
        self._log_widget.setMinimumHeight(200)
        splitter.addWidget(self._footer_splitter)

        widget = QWidget(self)
        layout = QHBoxLayout(widget)
        layout.addWidget(splitter)
        widget.setLayout(layout)

        self.setCentralWidget(widget)
        self.setMinimumWidth(700)
        self.resize(800, 600)

        # Calling directly from the constructor gets you wrong size information
        # noinspection PyCallByClass,PyTypeChecker
        QTimer.singleShot(500, self._update_widget_sizes)

    def _update_widget_sizes(self):
        max_footer_height = self.centralWidget().height() * 0.4
        self._footer_splitter.setMaximumHeight(max_footer_height)

    def resizeEvent(self, qresizeevent):
        super(BusMonitorWindow, self).resizeEvent(qresizeevent)
        self._update_widget_sizes()

    def _update_stat(self):
        bus_load, ts_mono = self._traffic_stat.get_frames_per_second()

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
        while True:
            item = self._get_frame()
            if item is None:
                break
            direction, frame = item
            self._traffic_stat.add_frame(direction, frame)
            # There is no need to maintain a second queue actually; should be refactored
            self._log_widget.add_item_async((direction, frame))

        bus_load, _ = self._traffic_stat.get_frames_per_second()
        self._stat_display.setText('%d / %d / %d' % (self._traffic_stat.tx, self._traffic_stat.rx, bus_load))

    def _decode_transfer_at_row(self, row):
        try:
            rows, text = decode_transfer_from_frame(row, partial(row_to_frame, self._log_widget.table))
        except Exception as ex:
            text = 'Transfer could not be decoded:\n' + str(ex)
            rows = [row]

        self._decoded_message_box.setPlainText(text.strip())

    def _update_measurement_display(self, selected_rows_cols):
        if not selected_rows_cols:
            return

        min_row = min([row for row, _ in selected_rows_cols])
        max_row = max([row for row, _ in selected_rows_cols])

        if min_row == max_row:
            self._decode_transfer_at_row(min_row)

        def get_ts_diff(row_earlier, row_later):
            e = self._log_widget.table.item(row_earlier, 1).text()
            l = self._log_widget.table.item(row_later, 1).text()
            return TimestampRenderer.compute_timestamp_difference(e, l)

        def get_load_str(num_frames, dt):
            if dt >= 1e-6:
                return 'average load %.1f FPS' % (max(num_frames - 1, 1) / dt)
            return 'average load is unknown'

        if min_row == max_row:
            num_frames = min_row
            dt = get_ts_diff(0, min_row)
            flash(self, '%d frames from beginning, %.3f sec since first frame, %s',
                  num_frames, dt, get_load_str(num_frames, dt))
        else:
            num_frames = max_row - min_row + 1
            dt = get_ts_diff(min_row, max_row)
            flash(self, '%d frames, timedelta %.6f sec, %s',
                  num_frames, dt, get_load_str(num_frames, dt))

    def _context_menu_requested(self, pos):
        menu = QMenu(self)

        row_index = self._log_widget.table.rowAt(pos.y())
        if row_index >= 0:
            action_show_definition = QAction(get_icon('file-code-o'), 'Open data type &definition', self)
            action_show_definition.triggered.connect(lambda: self._show_data_type_definition(row_index))
            menu.addAction(action_show_definition)
            menu.popup(self._log_widget.table.mapToGlobal(pos))

    def _show_data_type_definition(self, row):
        try:
            data_type_name = self._log_widget.table.item(row, self._log_widget.table.columnCount() - 1).text()
            definition = uavcan.TYPENAMES[data_type_name].source_text
        except Exception as ex:
            show_error('Data type lookup error', 'Could not load data type definition', ex, self)
            return

        win = QDialog(self)
        win.setAttribute(Qt.WA_DeleteOnClose)
        view = QPlainTextEdit(win)
        view.setReadOnly(True)
        view.setFont(get_monospace_font())
        view.setPlainText(definition)
        view.setLineWrapMode(QPlainTextEdit.NoWrap)
        layout = QVBoxLayout(win)
        layout.addWidget(view)
        win.setWindowTitle('Data type definition [%s]' % data_type_name)
        win.setLayout(layout)
        win.resize(600, 300)
        win.show()
