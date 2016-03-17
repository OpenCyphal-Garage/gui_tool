#
# Copyright (C) 2016  UAVCAN Development Team  <uavcan.org>
#
# This software is distributed under the terms of the MIT License.
#
# Author: Pavel Kirienko <pavel.kirienko@zubax.com>
#

import os
import re
import pkg_resources
import queue
from PyQt5.QtWidgets import QTableWidget, QTableWidgetItem, QAbstractItemView, QHeaderView, QApplication, QWidget, \
    QComboBox, QCompleter, QPushButton, QHBoxLayout, QVBoxLayout, QMessageBox
from PyQt5.QtCore import Qt, QTimer, QStringListModel
from PyQt5.QtGui import QColor, QKeySequence, QFont, QFontInfo, QIcon
from logging import getLogger
import qtawesome
from functools import partial


logger = getLogger(__name__)


def show_error(title, text, informative_text, parent=None):
    mbox = QMessageBox(parent)

    mbox.setWindowTitle(str(title))
    mbox.setText(str(text))
    if informative_text:
        mbox.setInformativeText(str(informative_text))

    mbox.setIcon(QMessageBox.Critical)
    mbox.setStandardButtons(QMessageBox.Ok)

    mbox.exec()


def request_confirmation(title, text, parent=None):
    reply = QMessageBox(parent).question(parent, title, text, QMessageBox().Yes | QMessageBox().No)
    return reply == QMessageBox().Yes


class BasicTable(QTableWidget):
    class Column:
        def __init__(self, name, renderer, resize_mode=QHeaderView.ResizeToContents,
                     searchable=True, filterable=None):
            self.name = name
            self.resize_mode = resize_mode
            self.render = renderer
            self.searchable = searchable
            self.filterable = filterable if filterable is not None else self.searchable

    def __init__(self, parent, columns, multi_line_rows=False, font=None):
        super(BasicTable, self).__init__(parent)

        self.columns = columns

        self.filter = None

        self.on_enter_pressed = lambda list_of_row_col_pairs: None

        self.setShowGrid(False)
        self.setWordWrap(False)
        self.verticalHeader().setVisible(False)
        self.setColumnCount(len(self.columns))
        self.setHorizontalHeaderLabels([x.name for x in self.columns])
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        if multi_line_rows:
            self.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
            self.setAlternatingRowColors(True)
        else:
            self.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
            self.verticalHeader().setDefaultSectionSize(20)             # TODO: I feel this is not very portable
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Fixed)

        for idx, col in enumerate(self.columns):
            self.horizontalHeader().setSectionResizeMode(idx, col.resize_mode)

        if font:
            self.setFont(font)

    def get_row_as_string(self, row, column_predicate=None):
        first = True
        out_string = ''
        for col in range(len(self.columns)):
            if column_predicate:
                if not column_predicate(self.columns[col]):
                    continue
            if not first:
                out_string += '\t'
            first = False
            out_string += str(self.item(row, col).text()) if self.item(row, col) else ''
        return out_string

    def apply_filter_to_row(self, row):
        if self.filter:
            text = self.get_row_as_string(row, lambda c: c.filterable)
            return self.filter.match(text)
        else:
            return True

    def set_row(self, row, model):
        for col, spec in enumerate(self.columns):
            value = spec.render(model)
            color = None
            if isinstance(value, tuple):
                value, color = value
            w = QTableWidgetItem(str(value))
            if color is not None:
                w.setBackground(color)
            w.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
            w.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            self.setItem(row, col, w)

        self.setRowHidden(row, not self.apply_filter_to_row(row))

    def keyPressEvent(self, qkeyevent):
        if qkeyevent.matches(QKeySequence.Copy):
            selected_rows = [x.row() for x in self.selectionModel().selectedRows()]
            logger.info('Copy to clipboard requested [%r rows]' % len(selected_rows))

            out_string = ''
            for row in selected_rows:
                out_string += self.get_row_as_string(row) + os.linesep

            if out_string:
                QApplication.clipboard().setText(out_string)
        else:
            super(BasicTable, self).keyPressEvent(qkeyevent)

        if qkeyevent.matches(QKeySequence.InsertParagraphSeparator):
            if self.hasFocus():
                self.on_enter_pressed([(x.row(), x.column()) for x in self.selectedIndexes()])

    def search(self, direction, matcher):
        if self.rowCount() == 0:
            return

        # Determining the start location
        selected_rows = [x.row() for x in self.selectionModel().selectedRows()]
        if selected_rows:
            # If at least one row is selected, search from there
            search_from_row = selected_rows[-1] if direction == 'up' else selected_rows[0]
        else:
            # If nothing is selected, search from beginning
            search_from_row = (self.rowCount() - 1) if direction == 'up' else 0

        search_from_row = max(0, search_from_row)
        logger.debug('Table search from %r, %r', search_from_row, direction)

        self.clearSelection()

        # Searching
        current_row = search_from_row + (-1 if direction == 'up' else 1)
        while current_row != search_from_row:
            if not self.isRowHidden(current_row):
                text = self.get_row_as_string(current_row, lambda c: c.searchable)
                if matcher.match(text):
                    self.selectRow(current_row)
                    self.scrollTo(self.model().index(current_row, 0))
                    return current_row

            current_row += -1 if direction == 'up' else 1
            if current_row >= self.rowCount():
                current_row = 0
            if current_row < 0:
                current_row = self.rowCount() - 1

    def set_filter(self, matcher):
        self.filter = matcher
        self.setUpdatesEnabled(False)

        for row in range(self.rowCount()):
            self.setRowHidden(row, not self.apply_filter_to_row(row))

        self.setUpdatesEnabled(True)


class CommitableComboBoxWithHistory(QComboBox):
    def __init__(self, parent):
        super(CommitableComboBoxWithHistory, self).__init__(parent)
        self.setInsertPolicy(QComboBox.InsertAtTop)
        self.setEditable(True)
        self.on_commit = lambda: None

    def keyPressEvent(self, qkeyevent):
        super(CommitableComboBoxWithHistory, self).keyPressEvent(qkeyevent)
        if qkeyevent.matches(QKeySequence.InsertParagraphSeparator):
            self.add_current_text_to_history()
            self.on_commit()

    def add_current_text_to_history(self):
        text = self.currentText()
        idx = self.findText(text)
        if idx >= 0:
            self.removeItem(idx)     # Moving to top, unique
        self.insertItem(0, text)
        self.setCurrentText(text)


class SearchMatcher:
    class BadPatternException(RuntimeError):
        pass

    def __init__(self, pattern, use_regex, case_sensitive, inverse=False):
        self.pattern = pattern
        self.use_regex = use_regex
        self.case_sensitive = case_sensitive
        self.inverse = inverse

    def _do_match(self, text):
        if self.use_regex:
            try:
                flags = re.UNICODE
                if not self.case_sensitive:
                    flags |= re.IGNORECASE
                return bool(re.findall(self.pattern, text, flags=flags))
            except Exception as ex:
                logger.warning('Regular expression match failed', exc_info=True)
                raise self.BadPatternException(str(ex))
        else:
            if self.case_sensitive:
                pattern = self.pattern
            else:
                pattern = self.pattern.lower()
                text = text.lower()
            return pattern in text

    def match(self, text):
        out = self._do_match(text)
        return out if not self.inverse else not out


class SearchMatcherChain:
    def __init__(self):
        self.matchers = []

    def append(self, m):
        self.matchers.append(m)

    def match(self, text):
        if len(self.matchers) > 0:
            return all([m.match(text) for m in self.matchers])
        else:
            return True


class SearchBarComboBox(CommitableComboBoxWithHistory):
    def __init__(self, parent, completion_model=None):
        super(SearchBarComboBox, self).__init__(parent)

        self.setFont(get_monospace_font())
        self.setToolTip('Enter the search pattern here')
        completer = QCompleter(self)
        completer.setCaseSensitivity(Qt.CaseSensitive)
        if completion_model is not None:
            completer.setModel(completion_model)
        else:
            completer.setModel(self.model())
        self.setCompleter(completer)


class SearchBar(QWidget):
    def __init__(self, parent):
        super(SearchBar, self).__init__(parent)

        self._default_search_direction = 'down'

        self.show_search_bar_button = \
            make_icon_button('search', 'Show search bar', self, checkable=True,
                             on_clicked=lambda: self.setVisible(self.show_search_bar_button.isChecked()))

        self._bar = SearchBarComboBox(self)
        self._bar.on_commit = lambda: self._do_search(self._default_search_direction)

        self._use_regex = make_icon_button('code', 'Search using regular expressions', self,
                                           checkable=True)

        self._case_sensitive = make_icon_button('text-height', 'Search query is case sensitive', self,
                                                checkable=True)

        self._button_search_down = make_icon_button('caret-down', 'Search down', self,
                                                    on_clicked=partial(self._do_search, 'down'))

        self._button_search_up = make_icon_button('caret-up', 'Search up', self,
                                                  on_clicked=partial(self._do_search, 'up'))

        self.on_search = lambda *_: None

        layout = QHBoxLayout(self)
        layout.addWidget(self._bar, 1)
        layout.addWidget(self._button_search_down)
        layout.addWidget(self._button_search_up)
        layout.addWidget(self._use_regex)
        layout.addWidget(self._case_sensitive)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)
        self.setVisible(False)

    def keyPressEvent(self, qkeyevent):
        super(SearchBar, self).keyPressEvent(qkeyevent)
        if qkeyevent.key() == Qt.Key_Escape:
            self.setVisible(False)
            self.show_search_bar_button.setChecked(False)

    def show(self):
        self.setVisible(True)
        self.show_search_bar_button.setChecked(True)
        self._bar.setFocus(Qt.OtherFocusReason)

    def _do_search(self, direction):
        self._default_search_direction = direction
        self._bar.add_current_text_to_history()

        text = str(self._bar.currentText())
        if not text:
            return

        logger.debug('Search request %r: %r', direction, text)

        matcher = SearchMatcher(text, self._use_regex.isChecked(), self._case_sensitive.isChecked())
        try:
            result = self.on_search(direction, matcher)
        except SearchMatcher.BadPatternException as ex:
            flash(self, 'Invalid search pattern: %s', ex, duration=10)
        else:
            if result is None:
                flash(self, 'Nothing found', duration=10)


class FilterBar(QWidget):
    class Filter(QWidget):
        def __init__(self, parent, pattern_completion_model):
            super(FilterBar.Filter, self).__init__(parent)

            self.on_commit = lambda: None
            self.on_remove = lambda _: None

            self._remove_button = make_icon_button('remove', 'Remove this filter', self,
                                                   on_clicked=lambda: self.on_remove(self))

            self._bar = SearchBarComboBox(self, pattern_completion_model)
            self._bar.on_commit = self._on_commit
            self._bar.setFocus(Qt.OtherFocusReason)

            self._apply_button = make_icon_button('check', 'Apply this filter expression [Enter]', self,
                                                  on_clicked=self._on_commit)

            self._inverse_button = make_icon_button('random', 'Negate filter', self, checkable=True,
                                                    on_clicked=self._on_commit)

            self._regex_button = make_icon_button('code', 'Use regular expressions', self, checkable=True,
                                                  checked=True, on_clicked=self._on_commit)

            self._case_sensitive_button = make_icon_button('text-height', 'Filter expression is case sensitive', self,
                                                           checkable=True, on_clicked=self._on_commit)

            layout = QHBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(self._remove_button)
            layout.addWidget(self._bar, 1)
            layout.addWidget(self._apply_button)
            layout.addWidget(self._inverse_button)
            layout.addWidget(self._regex_button)
            layout.addWidget(self._case_sensitive_button)
            self.setLayout(layout)

        def _on_commit(self):
            self._bar.add_current_text_to_history()
            self.on_commit()

        def keyPressEvent(self, qkeyevent):
            super(FilterBar.Filter, self).keyPressEvent(qkeyevent)
            if qkeyevent.key() == Qt.Key_Escape:
                self.on_remove(self)

        def make_matcher(self):
            matcher = SearchMatcher(self._bar.currentText(),
                                    use_regex=self._regex_button.isChecked(),
                                    case_sensitive=self._case_sensitive_button.isChecked(),
                                    inverse=self._inverse_button.isChecked())
            return matcher

    def __init__(self, parent):
        super(FilterBar, self).__init__(parent)

        self.add_filter_button = make_icon_button('filter', 'Add filter', self, on_clicked=self._on_add_filter)

        self.on_filter = lambda *_: None

        self._filters = []

        self._pattern_completion_model = QStringListModel(self)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(self._layout)
        self.setVisible(False)

    def _do_filter(self):
        if len(self._filters) > 0:
            chain = SearchMatcherChain()
            for m in self._filters:
                chain.append(m.make_matcher())
            logger.info('Applying chain of %d filters', len(chain.matchers))
            try:
                self.on_filter(chain)
            except SearchMatcher.BadPatternException as ex:
                flash(self, 'Invalid filter pattern: %s' % ex, duration=10)
        else:
            self.on_filter(None)

    def _on_add_filter(self):
        new_filter = self.Filter(self, self._pattern_completion_model)
        new_filter.on_remove = self._on_remove_filter
        new_filter.on_commit = self._do_filter

        self._filters.append(new_filter)
        self._layout.addWidget(new_filter)

        self.setVisible(True)

    def _on_remove_filter(self, instance):
        orig_len = len(self._filters)
        self._filters.remove(instance)
        assert(orig_len - 1 == len(self._filters))

        self._layout.removeWidget(instance)
        instance.setParent(None)
        instance.deleteLater()

        self.setVisible(len(self._filters) > 0)

        self._do_filter()                           # Re-applying all remaining filters on removal


class LabelWithIcon(QPushButton):
    def __init__(self, icon, text, parent):
        if isinstance(icon, str):
            icon = get_icon(icon)
        super(LabelWithIcon, self).__init__(icon, text, parent)
        self.setEnabled(False)


class RealtimeLogWidget(QWidget):
    def __init__(self, parent, started_by_default=False, pre_redraw_hook=None, **table_options):
        super(RealtimeLogWidget, self).__init__(parent)

        self.on_selection_changed = None

        self.pre_redraw_hook = pre_redraw_hook or (lambda: None)

        self._table = BasicTable(self, **table_options)
        self._table.selectionModel().selectionChanged.connect(self._call_on_selection_changed)

        self._clear_button = make_icon_button('trash-o', 'Clear', self, on_clicked=self._clear)

        self._pause = make_icon_button('pause', 'Pause updates; data received while paused will not be lost', self,
                                       checkable=True)

        self._start_button = make_icon_button('video-camera', 'Start/stop capturing', self,
                                              checkable=True,
                                              checked=started_by_default,
                                              on_clicked=self._on_start_button_clicked)

        self._search_bar = SearchBar(self)
        self._search_bar.on_search = self._search

        self._filter_bar = FilterBar(self)
        self._filter_bar.on_filter = self._table.set_filter

        self._row_count = LabelWithIcon(get_icon('list'), '0', self)
        self._row_count.setToolTip('Row count')

        self._redraw_timer = QTimer(self)
        self._redraw_timer.setSingleShot(False)
        self._redraw_timer.timeout.connect(self._redraw)
        self._redraw_timer.start(100)

        self._queue = queue.Queue()

        layout = QVBoxLayout(self)

        controls_layout = QHBoxLayout(self)
        controls_layout.addWidget(self._start_button)
        controls_layout.addWidget(self._pause)
        controls_layout.addWidget(self._clear_button)
        controls_layout.addWidget(self._search_bar.show_search_bar_button)
        controls_layout.addWidget(self._filter_bar.add_filter_button)

        self._custom_area_layout = QHBoxLayout(self)
        self._custom_area_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.addLayout(self._custom_area_layout, 1)
        controls_layout.addStretch()

        controls_layout.addWidget(self._row_count)

        layout.addLayout(controls_layout)
        layout.addWidget(self._search_bar)
        layout.addWidget(self._filter_bar)
        layout.addWidget(self._table, 1)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

    def keyPressEvent(self, qkeyevent):
        super(RealtimeLogWidget, self).keyPressEvent(qkeyevent)
        if qkeyevent.matches(QKeySequence.Find):
            self._search_bar.show()

    def _search(self, *args, **kwargs):
        self._pause.setChecked(True)
        self._table.search(*args, **kwargs)

    def _clear(self):
        self._table.setRowCount(0)
        self._row_count.setText(str(self._table.rowCount()))

    def _call_on_selection_changed(self):
        if not self.on_selection_changed:
            return

        selected_rows_cols = [(x.row(), x.column()) for x in self._table.selectedIndexes()]
        self.on_selection_changed(selected_rows_cols)

    def _redraw(self):
        self.pre_redraw_hook()

        if self.started:
            self._table.setUpdatesEnabled(False)

            do_scroll = False
            if not self.paused:
                while True:
                    try:
                        item = self._queue.get_nowait()
                    except queue.Empty:
                        break

                    row = self._table.rowCount()
                    self._table.insertRow(row)
                    self._table.set_row(row, item)
                    do_scroll = True

            self._table.setUpdatesEnabled(True)

            if do_scroll:
                self._table.scrollToBottom()

            self._row_count.setText(str(self._table.rowCount()))
        else:
            # Discarding inputs
            while self._queue.qsize() > 0:
                self._queue.get_nowait()

    def _on_start_button_clicked(self):
        self._pause.setChecked(False)

    def add_item_async(self, item):
        self._queue.put_nowait(item)

    @property
    def table(self):
        return self._table

    @property
    def paused(self):
        return self._pause.isChecked()

    @property
    def started(self):
        return self._start_button.isChecked()

    @property
    def custom_area_layout(self):
        return self._custom_area_layout


def get_icon(name):
    return qtawesome.icon('fa.' + name)


def make_icon_button(icon_name, tool_tip, parent, checkable=False, checked=False, on_clicked=None, text=''):
    b = QPushButton(text, parent)
    b.setFocusPolicy(Qt.NoFocus)
    if icon_name:
        b.setIcon(get_icon(icon_name))
    b.setToolTip(tool_tip)
    if checkable:
        b.setCheckable(True)
        b.setChecked(checked)
    if on_clicked:
        b.clicked.connect(on_clicked)
    return b


def map_7bit_to_color(value):
    value = int(value) & 0x7f

    red = ((value >> 5) & 0b11) * 48        # 2 bits to red
    green = ((value >> 2) & 0b111) * 12     # 3 bits to green, because human eye is more sensitive in this wavelength
    blue = (value & 0b11) * 48              # 2 bits to blue

    col = QColor()
    col.setRgb(0xFF - red, 0xFF - green, 0xFF - blue)
    return col


def get_monospace_font():
    preferred = ['Consolas', 'DejaVu Sans Mono', 'Monospace', 'Lucida Console', 'Monaco']
    for name in preferred:
        font = QFont(name)
        if QFontInfo(font).fixedPitch():
            logger.debug('Preferred monospace font: %r', font.toString())
            return font

    font = QFont()
    font.setStyleHint(QFont().Monospace)
    font.setFamily('monospace')
    logger.debug('Using fallback monospace font: %r', font.toString())
    return font


def get_app_icon():
    global _APP_ICON_OBJECT
    try:
        return _APP_ICON_OBJECT
    except NameError:
        pass
    # noinspection PyBroadException
    try:
        fn = pkg_resources.resource_filename('uavcan_gui_tool', os.path.join('icons', 'logo_256x256.png'))
        _APP_ICON_OBJECT = QIcon(fn)
    except Exception:
        logger.error('Could not load icon', exc_info=True)
        _APP_ICON_OBJECT = QIcon()
    return _APP_ICON_OBJECT


def flash(sender, message, *format_args, duration=0):
    sender.window().statusBar().showMessage(message % format_args, duration * 1000)
