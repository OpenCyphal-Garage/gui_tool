#!/usr/bin/env python3
#
# Pavel Kirienko, 2016 <pavel.kirienko@zubax.com>
#

import logging
import sys

if __name__ == '__main__':
    logging.basicConfig(stream=sys.stderr, level=logging.DEBUG,
                        format='%(asctime)s %(levelname)s %(name)s: %(message)s')
    logging.getLogger('uavcan').setLevel(logging.INFO)

import uavcan
import numpy
import time
import os
import multiprocessing
import queue
import collections
# Qt4 must be imported after uavcan, because it seems to add a new global named 'basestring' which
# breaks Python version detection in 'pkg_resources', which subsequently tries to import 'cStringIO' on Py3,
# which fails. Travesty.
from PyQt4 import QtGui
from PyQt4.QtCore import Qt, QTimer, QRectF
from PyQt4.QtGui import QColor, QVBoxLayout, QHBoxLayout, QWidget, QDialog, QGridLayout
from pyqtgraph import PlotWidget, mkPen


class ReceivedMessage:
    REFERENCE_TIME_MONOTONIC = None

    def __init__(self, transfer):
        self.fields = self._extract_fields(transfer.payload)
        self.source_node_id = transfer.source_node_id
        self.ts_monotonic = transfer.ts_monotonic
        self.data_type_name = str(transfer.payload.type)

    def _extract_fields(self, x):
        if isinstance(x, (int, float, bool, str, bytes)):
            return x
        if isinstance(x, uavcan.transport.Void) or isinstance(x.type, uavcan.dsdl.parser.VoidType): # HACK
            return None
        if isinstance(x.type, uavcan.dsdl.parser.PrimitiveType):
            return x.value
        if isinstance(x.type, uavcan.dsdl.parser.CompoundType):
            return {name: self._extract_fields(value) for name, value in x.fields.items()}
        if isinstance(x.type, uavcan.dsdl.parser.ArrayType):
            val = [self._extract_fields(y) for y in x]
            try:
                val = bytes(val)        # String handling heuristic
            except Exception:
                pass
            return val
        raise Exception('Invalid field type: %s' % x.type)

    @staticmethod
    def _extract_field_by_path(fields, path):
        head, tail = path[0], path[1:]
        try:
            value = fields[head]            # Trying as mapping
        except TypeError:
            try:
                value = fields[int(head)]   # Trying as iterable
            except IndexError:
                return
        if tail:
            return ReceivedMessage._extract_field_by_path(value, tail)
        return value

    def get_timestamp(self):
        if not ReceivedMessage.REFERENCE_TIME_MONOTONIC:
            ReceivedMessage.REFERENCE_TIME_MONOTONIC = time.monotonic()
        return self.ts_monotonic - ReceivedMessage.REFERENCE_TIME_MONOTONIC

    def _make_curve_name(self, field_path, discriminator_fields):
        s = '%-3d %s.%s' % (self.source_node_id, self.data_type_name, field_path)
        for key, val in discriminator_fields.items():
            try:
                val = val.decode()
            except Exception:
                pass
            s += ' %s=%r' % (key, val)
        return s.strip()

    def get_field_by_path(self, path):
        return self._extract_field_by_path(self.fields, path.split('.'))

    def get_field_and_curve_name(self, field_path, discriminator_field_pathes=None):
        discriminator_fields = collections.OrderedDict()
        for dfp in discriminator_field_pathes:
            discriminator_fields[dfp] = self.get_field_by_path(dfp)
        name = self._make_curve_name(field_path, discriminator_fields)
        field = self.get_field_by_path(field_path)
        return field, name


class CurveMatcher:
    def __init__(self, data_type_name, field_path, discriminator_fields=None, source_node_id=None,
                 multiplier=None, offset=None):
        self.data_type_name = data_type_name
        self.field_path = field_path
        self.discriminator_fields = discriminator_fields or []  # [Field, (Value or None)]
        self.source_node_id = source_node_id or 0
        self.multiplier = multiplier if multiplier is not None else 1
        self.offset = offset or 0

    def match(self, msg):
        # Type name validation
        if msg.data_type_name != self.data_type_name:
            return False
        # Source node ID filtering
        if self.source_node_id and (self.source_node_id != msg.source_node_id):
            return False
        # Discriminator field filtering
        for key, reference in self.discriminator_fields:
            if reference is None:
                continue
            real_value = msg.get_field_by_path(key)
            try:
                real_value_decoded = real_value.decode()        # String handling heuristic
            except Exception:
                real_value_decoded = real_value
            if reference != real_value and reference != real_value_decoded:
                return False
        return True

    def extract_curve_name_x_y(self, msg):
        y, name = msg.get_field_and_curve_name(self.field_path, [fld for fld, _ in self.discriminator_fields])
        x = msg.get_timestamp()
        y = float(y) * self.multiplier + self.offset
        return name, x, y


def list_message_data_type_names_with_dtid():
    # Custom data type mappings must be configured in the library
    message_types = []
    for (dtid, kind), dtype in uavcan.DATATYPES.items():
        if dtid is not None and kind == uavcan.dsdl.CompoundType.KIND_MESSAGE:
            message_types.append(str(dtype))
    return list(sorted(message_types))


def list_recursive_fields(dt):
    dt = uavcan.TYPENAMES[dt] if isinstance(dt, str) else dt  # This way we can accept either type or its name
    if hasattr(dt, 'category') and dt.category == dt.CATEGORY_ARRAY:
        out = [('', dt)]
        nested = list_recursive_fields(dt.value_type)
        if nested:
            for x in range(dt.max_size):
                out += [(('%d.' % x) + n, t) for n, t in nested]
        else:
            out += [(str(x), dt.value_type) for x in range(dt.max_size)]
        return out
    out = []
    for field in getattr(dt, 'fields', []):
        subfields = list_recursive_fields(field.type)
        if subfields:
            out += [('.'.join([field.name, sf]).strip('.'), dtype) for sf, dtype in subfields]
        elif hasattr(field.type, 'category') and field.type.category != field.type.CATEGORY_VOID:
            out.append((field.name, field.type))
    return out


class CurveMatcherView(QWidget):
    def __init__(self, model, parent):
        super(CurveMatcherView, self).__init__(parent)

        self.on_remove = lambda: None
        btn_remove = QtGui.QPushButton('', self)
        btn_remove.setIcon(QtGui.QIcon.fromTheme('list-remove'))
        btn_remove.clicked.connect(lambda: self.on_remove())
        btn_remove.setToolTip('Remove this curve matcher')
        btn_remove.setMaximumWidth(btn_remove.height())

        spin_multiplier = QtGui.QDoubleSpinBox(self)
        spin_multiplier.setMaximum(1e9)
        spin_multiplier.setMinimum(-1e9)
        spin_multiplier.setDecimals(6)
        spin_multiplier.setValue(model.multiplier)
        spin_multiplier.setToolTip('Multiplier')
        def update_mult():
            model.multiplier = float(spin_multiplier.value())
        spin_multiplier.valueChanged.connect(update_mult)

        spin_offset = QtGui.QDoubleSpinBox(self)
        spin_offset.setMaximum(1e6)
        spin_offset.setMinimum(-1e6)
        spin_offset.setDecimals(6)
        spin_offset.setValue(model.offset)
        spin_offset.setToolTip('Offset')
        def update_offs():
            model.offset = float(spin_offset.value())
        spin_offset.valueChanged.connect(update_offs)

        def add_box(contents, tooltip, stretch=0):
            w = QtGui.QLineEdit(str(contents), self)
            w.setReadOnly(True)
            w.setToolTip(tooltip)
            w.setMinimumWidth(20)
            layout.addWidget(w, stretch)

        layout = QHBoxLayout()
        layout.addWidget(btn_remove)

        add_box(model.source_node_id if model.source_node_id > 0 else 'Any', 'Node ID')
        add_box(model.data_type_name, 'UAVCAN data type name', 1)
        add_box(model.field_path, 'Name of the field to plot values from', 1)
        add_box(model.discriminator_fields, 'Discriminators', 1)

        layout.addWidget(spin_multiplier)
        layout.addWidget(spin_offset)
        self.setLayout(layout)


class NewCurveMatcherWindow(QDialog):
    def __init__(self, parent, get_available_types, callback):
        # Parent
        super(NewCurveMatcherWindow, self).__init__(parent)
        self.setWindowTitle('New Curve Matcher')
        self.setWindowIcon(APP_ICON)
        self.setModal(True)

        self._callback = callback

        # Widgets
        self._source_node_id = QtGui.QSpinBox(self)
        self._source_node_id.setMinimum(0)
        self._source_node_id.setMaximum(127)
        self._source_node_id.setToolTip('Set to zero to match any node')

        def update_data_types():
            val = self._dtname.currentText()
            self._dtname.clear()
            if self._show_only_active_data_types.checkState():
                types = list(get_available_types())
            else:
                types = list_message_data_type_names_with_dtid()
            self._dtname.addItems(types)
            self._dtname.setEditText(val)

        self._show_only_active_data_types = QtGui.QCheckBox('Show only active data types in the box below', self)
        self._show_only_active_data_types.setChecked(True)
        self._show_only_active_data_types.stateChanged.connect(update_data_types)

        self._dtname = QtGui.QComboBox(self)
        self._dtname.setEditable(True)
        self._dtname.setAutoCompletion(True)
        self._dtname.setAutoCompletionCaseSensitivity(Qt.CaseSensitive)
        self._dtname.setInsertPolicy(QtGui.QComboBox.NoInsert)
        self._dtname.setSizeAdjustPolicy(QtGui.QComboBox.AdjustToContents)
        self._dtname.setToolTip('UAVCAN data type')
        self._dtname.addItems(list(get_available_types()))
        self._dtname.editTextChanged.connect(self._update_data_type)

        self._field_path = QtGui.QComboBox(self)
        self._field_path.setEditable(True)
        self._field_path.setAutoCompletion(True)
        self._field_path.setInsertPolicy(QtGui.QComboBox.NoInsert)
        self._field_path.setSizeAdjustPolicy(QtGui.QComboBox.AdjustToContents)
        self._field_path.setToolTip('Field to plot values from')

        self._discriminators = QtGui.QTableWidget()
        self._discriminators.setMinimumWidth(400)
        self._discriminators.setShowGrid(False)
        self._discriminators.verticalHeader().setVisible(False)

        self._multiplier = QtGui.QDoubleSpinBox(self)
        self._multiplier.setMaximum(1e9)
        self._multiplier.setMinimum(-1e9)
        self._multiplier.setValue(1)
        self._multiplier.setDecimals(6)
        self._multiplier.setToolTip('Plot Value = Field Value * Multiplier + Offset')

        self._offset = QtGui.QDoubleSpinBox(self)
        self._offset.setMaximum(1e6)
        self._offset.setMinimum(-1e6)
        self._offset.setDecimals(6)
        self._offset.setToolTip('Plot Value = Field Value * Multiplier + Offset')

        # Controls
        button_cancel = QtGui.QPushButton('Cancel', self)
        button_cancel.clicked.connect(self.close)

        button_ok = QtGui.QPushButton('OK', self)
        button_ok.clicked.connect(self._finalize)

        # Layout
        inputs_layout = QGridLayout()
        inputs_layout_row = 1

        def add_input(text, widget):
            nonlocal inputs_layout_row
            if text:
                label = QtGui.QLabel(text + ':')
                label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                inputs_layout.addWidget(label, inputs_layout_row, 1)
            inputs_layout.addWidget(widget, inputs_layout_row, 2)
            inputs_layout_row += 1

        add_input('Node ID', self._source_node_id)
        add_input(None, self._show_only_active_data_types)
        add_input('Data Type', self._dtname)
        add_input('Field', self._field_path)
        add_input('Discriminators', self._discriminators)
        add_input('Multiplier', self._multiplier)
        add_input('Offset', self._offset)

        buttons_layout = QHBoxLayout()
        buttons_layout.addWidget(button_cancel)
        buttons_layout.addWidget(button_ok)

        main_layout = QVBoxLayout()
        main_layout.addLayout(inputs_layout, 1)
        main_layout.addLayout(buttons_layout)
        self.setLayout(main_layout)

        self._update_data_type()

    def _get_selected_data_type(self):
        return str(self._dtname.currentText())

    def _reset_discr_table(self):
        self._discriminators.clear()
        try:
            fields_with_types = list_recursive_fields(self._get_selected_data_type())
        except Exception:
            return
        fields_with_types = [(f, t) for f, t in fields_with_types
                             if (t.category == t.CATEGORY_PRIMITIVE and
                                 t.kind in (t.KIND_BOOLEAN, t.KIND_UNSIGNED_INT, t.KIND_SIGNED_INT)) or
                             (t.category == t.CATEGORY_ARRAY and
                              t.value_type.category == t.value_type.CATEGORY_PRIMITIVE and
                              t.value_type.bitlen in (7, 8))]

        self._discriminators.setColumnCount(3)
        self._discriminators.setHorizontalHeaderLabels(['Field', 'Filter', 'Value'])
        self._discriminators.horizontalHeader().setResizeMode(0, QtGui.QHeaderView.Stretch)
        self._discriminators.horizontalHeader().setResizeMode(1, QtGui.QHeaderView.ResizeToContents)
        self._discriminators.horizontalHeader().setResizeMode(2, QtGui.QHeaderView.ResizeToContents)
        self._discriminators.setRowCount(len(fields_with_types))

        for i, (fname, ftype) in enumerate(fields_with_types):
            # Activation checkbox
            active = QtGui.QCheckBox(fname, self)
            self._discriminators.setCellWidget(i, 0, active)

            # Value configuration checkbox
            widget = None  # Canary
            if ftype.category == ftype.CATEGORY_PRIMITIVE:
                if ftype.kind == ftype.KIND_BOOLEAN:
                    widget = QtGui.QCheckBox('True/False', self)
                else:
                    if ftype.kind in (ftype.KIND_UNSIGNED_INT, ftype.KIND_SIGNED_INT):
                        widget = QtGui.QSpinBox(self)
                    elif ftype.kind == ftype.KIND_FLOAT:
                        widget = QtGui.QDoubleSpinBox(self)
                    widget.setMinimum(max(-2**31, ftype.value_range[0]))
                    widget.setMaximum(min(2**31 - 1, ftype.value_range[1]))
            else:
                widget = QtGui.QLineEdit(self)
            widget.setEnabled(False)
            self._discriminators.setCellWidget(i, 2, widget)

            # Filter/discriminator mode selection
            def make_filt_closure(widget, filt):
                def impl():
                    widget.setEnabled(filt.isChecked())
                return impl
            filt = QtGui.QCheckBox('', self)
            filt.setIcon(QtGui.QIcon.fromTheme('emblem-favorite'))
            filt.clicked.connect(make_filt_closure(widget, filt))
            self._discriminators.setCellWidget(i, 1, filt)

        self._discriminators.resizeColumnsToContents()
        self._discriminators.resizeRowsToContents()

    def _update_data_type(self):
        self._field_path.clear()
        self._reset_discr_table()
        try:
            fields = list_recursive_fields(self._get_selected_data_type())
            self._field_path.addItems([name for name, dt in fields if dt.category == dt.CATEGORY_PRIMITIVE])
        except Exception:
            pass

    def _finalize(self):
        dtname = self._get_selected_data_type()
        field = str(self._field_path.currentText())
        node_id = int(self._source_node_id.value())
        multiplier = float(self._multiplier.value())
        offset = float(self._offset.value())

        discriminators = []
        for row in range(self._discriminators.rowCount()):
            name_cell = self._discriminators.cellWidget(row, 0)
            enabled = bool(name_cell.checkState())
            name = name_cell.text()
            checked = bool(self._discriminators.cellWidget(row, 1).checkState())
            val_cell = self._discriminators.cellWidget(row, 2)
            try:
                value = str(val_cell.text())
            except Exception:
                try:
                    value = val_cell.value()
                except Exception:
                    value = bool(val_cell.checkState())
            if enabled:
                discriminators.append((name, (value if checked else None)))

        matcher = CurveMatcher(dtname, field, discriminator_fields=discriminators,
                               source_node_id=node_id, multiplier=multiplier, offset=offset)

        self._callback(matcher)
        self.close()


class Plotter(QWidget):
    MAX_DATA_POINTS_PER_CURVE = 200000

    COLORS = [Qt.red, Qt.green, Qt.blue,                        # RGB - http://ux.stackexchange.com/questions/79561
              Qt.yellow, Qt.cyan, Qt.magenta,                   # Close to RGB
              Qt.darkRed, Qt.darkGreen, Qt.darkBlue,            # Darker RGB
              Qt.darkYellow, Qt.darkCyan, Qt.darkMagenta,       # Close to RGB
              Qt.gray, Qt.darkGray]                             # Leftovers

    INITIAL_X_RANGE = 60

    def __init__(self, parent=None):
        # Parent
        super(Plotter, self).__init__(parent)
        self.setWindowTitle('UAVCAN Plotter')
        self.setWindowIcon(APP_ICON)

        # Redraw timer
        self._update_timer = QTimer()
        self._update_timer.timeout.connect(self._update)
        self._update_timer.setSingleShot(False)
        self._update_timer.start(30)

        # PyQtGraph
        self._plot_widget = PlotWidget()
        self._plot_widget.setBackground((0, 0, 0))
        self._legend = self._plot_widget.addLegend()
        self._plot_widget.setRange(xRange=(0, self.INITIAL_X_RANGE), padding=0)
        self._plot_widget.showButtons()
        self._plot_widget.enableAutoRange()
        self._plot_widget.showGrid(x=True, y=True, alpha=0.4)

        # Controls
        # https://specifications.freedesktop.org/icon-naming-spec/icon-naming-spec-latest.html
        button_add_matcher = QtGui.QPushButton('New matcher', self)
        button_add_matcher.setIcon(QtGui.QIcon.fromTheme('list-add'))
        button_add_matcher.setToolTip('Add new curve matcher')
        button_add_matcher.clicked.connect(
            lambda: NewCurveMatcherWindow(self, lambda: sorted(self._active_messages), self._add_curve_matcher).show())

        button_clear_plots = QtGui.QPushButton('Clear plots', self)
        button_clear_plots.setIcon(QtGui.QIcon.fromTheme('edit-clear'))
        button_clear_plots.setToolTip('Clear the plotting area')
        button_clear_plots.clicked.connect(lambda: self._remove_all_curves())

        def delete_all_matchers():
            self._curve_matchers = []
            for i in reversed(range(self._curve_matcher_container.count())):
                self._curve_matcher_container.itemAt(i).widget().deleteLater()
            self._remove_all_curves()

        button_delete_all_matchers = QtGui.QPushButton('Delete matchers', self)
        button_delete_all_matchers.setIcon(QtGui.QIcon.fromTheme('edit-delete'))
        button_delete_all_matchers.setToolTip('Delete all matchers')
        button_delete_all_matchers.clicked.connect(delete_all_matchers)

        self._autoscroll = QtGui.QCheckBox('Autoscroll', self)
        self._autoscroll.setChecked(True)
        self._max_x = self.INITIAL_X_RANGE

        # Layout
        control_panel = QHBoxLayout()
        control_panel.addWidget(button_add_matcher)
        control_panel.addWidget(button_clear_plots)
        control_panel.addWidget(self._autoscroll)
        control_panel.addStretch()
        control_panel.addWidget(button_delete_all_matchers)

        self._curve_matcher_container = QVBoxLayout()

        layout = QVBoxLayout()
        layout.addWidget(self._plot_widget, 1)
        layout.addLayout(control_panel)
        layout.addLayout(self._curve_matcher_container)
        self.setLayout(layout)

        # Logic
        self._color_index = 0
        self._curves = {}
        self._message_queue = multiprocessing.Queue()
        self._active_messages = set() # set(data type name)
        self._curve_matchers = []

        # Defaults
        self._add_curve_matcher(CurveMatcher('uavcan.protocol.debug.KeyValue', 'value', [('key', None)]))

    def _add_curve_matcher(self, matcher):
        self._curve_matchers.append(matcher)
        view = CurveMatcherView(matcher, self)

        def remove():
            self._curve_matchers.remove(matcher)
            self._curve_matcher_container.removeWidget(view)
            view.setParent(None)
            view.deleteLater()

        view.on_remove = remove
        self._curve_matcher_container.addWidget(view)

    def _update(self):
        # Processing messages
        while True:
            try:
                m = self._message_queue.get_nowait()
                self._process_message(m)
            except queue.Empty:
                break
        # Updating curves
        for curve in self._curves.values():
            if len(curve['x']):
                if len(curve['x']) > self.MAX_DATA_POINTS_PER_CURVE:
                    curve['x'] = curve['x'][-self.MAX_DATA_POINTS_PER_CURVE:]
                    curve['y'] = curve['y'][-self.MAX_DATA_POINTS_PER_CURVE:]
                assert len(curve['x']) == len(curve['y'])
                curve['plot'].setData(curve['x'], curve['y'])
                self._max_x = max(self._max_x, curve['x'][-1])
        # Updating view range
        if self._autoscroll.checkState():
            (xmin, xmax), _ = self._plot_widget.viewRange()
            diff = xmax - xmin
            xmax = self._max_x
            xmin = self._max_x - diff
            self._plot_widget.setRange(xRange=(xmin, xmax), padding=0)


    def _process_message(self, m):
        self._active_messages.add(m.data_type_name)
        for matcher in self._curve_matchers:
            if matcher.match(m):
                name, x, y = matcher.extract_curve_name_x_y(m)
                self._draw_curve(name, x, y)

    def _remove_all_curves(self):
        for curve in self._curves.values():
            self._plot_widget.removeItem(curve['plot'])
        self._plot_widget.clear()
        self._curves = {}
        self._color_index = 0
        self._legend.scene().removeItem(self._legend)
        self._legend = self._plot_widget.addLegend()

    def _draw_curve(self, name, x, y):
        if name not in self._curves:
            logging.info('Adding curve %r', name)
            color = self.COLORS[self._color_index % len(self.COLORS)]
            self._color_index += 1
            pen = mkPen(QColor(color), width=1)
            plot = self._plot_widget.plot(name=name, pen=pen)
            self._curves[name] = {'x': numpy.array([]), 'y': numpy.array([]), 'plot': plot}

        curve = self._curves[name]
        curve['x'] = numpy.append(curve['x'], [x] if isinstance(x, (float, int)) else x)
        curve['y'] = numpy.append(curve['y'], [y] if isinstance(y, (float, int)) else y)
        assert len(curve['x']) == len(curve['y'])

    def push_received_message(self, msg):
        self._message_queue.put_nowait(msg)


def node_process(iface, iface_kwargs, on_transfer_callback):
    logging.info('Starting the spinner process')

    # Initializing the node
    node = uavcan.make_node(iface, **iface_kwargs)  # Passive mode

    # Patching the node object to receive all messages from the bus
    # TODO: Add required logic to the library
    def call_handlers_replacement(transfer):
        if not transfer.service_not_message:
            on_transfer_callback(transfer)
    node._handler_dispatcher.call_handlers = call_handlers_replacement

    # Spinning the node
    while True:
        try:
            node.spin()
        except Exception:
            logging.error('Node spin exception', exc_info=True)


def list_ifaces():
    if sys.platform.lower() == 'linux':
        import glob
        ifaces = glob.glob('/dev/serial/by-id/*')
        with open('/proc/net/dev') as f:
            for line in f:
                if ':' in line:
                    name = line.split(':')[0].strip()
                    ifaces.insert(0 if 'can' in name else len(ifaces), name)
    else:
        try:
            import serial.tools.list_ports
            ifaces = [x for x, _, _ in serial.tools.list_ports.comports()]
        except ImportError:
            ifaces = []
    return ifaces


def get_iface_config():
    win = QDialog()
    win.setWindowTitle('CAN Interface Configuration')
    win.setWindowIcon(APP_ICON)

    combo = QtGui.QComboBox(win)
    combo.setEditable(True)
    combo.setAutoCompletion(True)
    combo.setAutoCompletionCaseSensitivity(Qt.CaseSensitive)
    combo.setInsertPolicy(QtGui.QComboBox.NoInsert)
    combo.setSizeAdjustPolicy(QtGui.QComboBox.AdjustToContents)
    combo.addItems(list_ifaces())

    bitrate = QtGui.QSpinBox()
    bitrate.setMaximum(1000000)
    bitrate.setMinimum(10000)
    bitrate.setValue(1000000)

    extra_args = QtGui.QLineEdit()

    ok = QtGui.QPushButton('OK', win)

    result = None
    kwargs = {}

    def on_ok():
        nonlocal result, kwargs
        a = str(extra_args.text())
        if a:
            try:
                kwargs = dict(eval(a))
            except Exception as ex:
                mbox = QtGui.QMessageBox(win)
                mbox.setWindowTitle('Invalid parameters')
                mbox.setText('Could not parse optional arguments')
                mbox.setInformativeText(str(ex))
                mbox.setIcon(QtGui.QMessageBox.Critical)
                mbox.setStandardButtons(QtGui.QMessageBox.Ok)
                mbox.exec()
                return
        kwargs['bitrate'] = int(bitrate.value())
        result = str(combo.currentText())
        win.close()

    ok.clicked.connect(on_ok)

    layout = QVBoxLayout()
    layout.addWidget(QtGui.QLabel('Select CAN interface or serial port for SLCAN:'))
    layout.addWidget(combo)
    layout.addWidget(QtGui.QLabel('Interface bitrate (SLCAN only):'))
    layout.addWidget(bitrate)
    layout.addWidget(QtGui.QLabel('Optional arguments (refer to Pyuavcan for info):'))
    layout.addWidget(extra_args)
    layout.addWidget(ok)
    win.setLayout(layout)
    win.exec()

    return result, kwargs


if __name__ == '__main__':
    app = QtGui.QApplication(sys.argv)

    APP_ICON = QtGui.QIcon(os.path.join(os.path.dirname(__file__), 'icon.png'))

    iface, kwargs = get_iface_config()
    if not iface:
        exit()

    plotter = Plotter()
    plotter.show()

    def on_transfer_callback(transfer):
        plotter.push_received_message(ReceivedMessage(transfer))

    multiprocessing.Process(target=node_process, daemon=True, args=(iface, kwargs, on_transfer_callback)).start()

    exit(app.exec_())
