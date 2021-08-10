#
# Copyright (C) 2016  UAVCAN Development Team  <uavcan.org>
#
# This software is distributed under the terms of the MIT License.
#
# Author: Pavel Kirienko <pavel.kirienko@zubax.com>
#

import logging
import multiprocessing
import os
import sys
import time
import tempfile

assert sys.version[0] == '3'

from argparse import ArgumentParser
parser = ArgumentParser(description='UAVCAN GUI tool')

parser.add_argument("--debug", action='store_true', help="enable debugging")
parser.add_argument("--dsdl", help="path to custom DSDL")

args = parser.parse_args()

#
# Configuring logging before other packages are imported
#
if args.debug:
    logging_level = logging.DEBUG
else:
    logging_level = logging.INFO

logging.basicConfig(stream=sys.stderr, level=logging_level,
                    format='%(asctime)s %(levelname)s %(name)s %(message)s')

log_file = tempfile.NamedTemporaryFile(mode='w', prefix='uavcan_gui_tool-', suffix='.log', delete=False)
file_handler = logging.FileHandler(log_file.name)
file_handler.setLevel(logging_level)
file_handler.setFormatter(logging.Formatter('%(asctime)s [%(process)d] %(levelname)-8s %(name)-25s %(message)s'))
logging.root.addHandler(file_handler)

logger = logging.getLogger(__name__.replace('__', ''))
logger.info('Spawned')

#
# Applying Windows-specific hacks
#
os.environ['PATH'] = os.environ['PATH'] + ';' + os.path.dirname(sys.executable)  # Otherwise it fails to load on Win 10

#
# Configuring multiprocessing.
# Start method must be configured globally, and only once. Using 'spawn' ensures full compatibility with Windoze.
# We need to check first if the start mode is already configured, because this code will be re-run for every child.
#
if multiprocessing.get_start_method(True) != 'spawn':
    multiprocessing.set_start_method('spawn')

#
# Importing other stuff once the logging has been configured
#
import pyuavcan_v0

from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QSplitter, QAction
from PyQt5.QtGui import QKeySequence, QDesktopServices
from PyQt5.QtCore import QTimer, Qt, QUrl

from .version import __version__
from .setup_window import run_setup_window
from .active_data_type_detector import ActiveDataTypeDetector
from . import update_checker

from .widgets import show_error, get_icon, get_app_icon
from .widgets.node_monitor import NodeMonitorWidget
from .widgets.local_node import LocalNodeWidget
from .widgets.log_message_display import LogMessageDisplayWidget
from .widgets.bus_monitor import BusMonitorManager
from .widgets.dynamic_node_id_allocator import DynamicNodeIDAllocatorWidget
from .widgets.file_server import FileServerWidget
from .widgets.node_properties import NodePropertiesWindow
from .widgets.console import ConsoleManager, InternalObjectDescriptor
from .widgets.subscriber import SubscriberWindow
from .widgets.plotter import PlotterManager
from .widgets.about_window import AboutWindow
from .widgets.can_adapter_control_panel import spawn_window as spawn_can_adapter_control_panel

from .panels import PANELS


NODE_NAME = 'org.pyuavcan_v0.gui_tool'


class MainWindow(QMainWindow):
    MAX_SUCCESSIVE_NODE_ERRORS = 1000

    # noinspection PyTypeChecker,PyCallByClass,PyUnresolvedReferences
    def __init__(self, node, iface_name):
        # Parent
        super(MainWindow, self).__init__()
        self.setWindowTitle('UAVCAN GUI Tool')
        self.setWindowIcon(get_app_icon())

        self._node = node
        self._successive_node_errors = 0
        self._iface_name = iface_name

        self._active_data_type_detector = ActiveDataTypeDetector(self._node)

        self._node_spin_timer = QTimer(self)
        self._node_spin_timer.timeout.connect(self._spin_node)
        self._node_spin_timer.setSingleShot(False)
        self._node_spin_timer.start(10)

        self._node_windows = {}  # node ID : window object

        self._node_monitor_widget = NodeMonitorWidget(self, node)
        self._node_monitor_widget.on_info_window_requested = self._show_node_window

        self._local_node_widget = LocalNodeWidget(self, node)
        self._log_message_widget = LogMessageDisplayWidget(self, node)
        self._dynamic_node_id_allocation_widget = DynamicNodeIDAllocatorWidget(self, node,
                                                                               self._node_monitor_widget.monitor)
        self._file_server_widget = FileServerWidget(self, node)

        self._plotter_manager = PlotterManager(self._node)
        self._bus_monitor_manager = BusMonitorManager(self._node, iface_name)
        # Console manager depends on other stuff via context, initialize it last
        self._console_manager = ConsoleManager(self._make_console_context)

        #
        # File menu
        #
        quit_action = QAction(get_icon('sign-out'), '&Quit', self)
        quit_action.setShortcut(QKeySequence('Ctrl+Shift+Q'))
        quit_action.triggered.connect(self.close)

        file_menu = self.menuBar().addMenu('&File')
        file_menu.addAction(quit_action)

        #
        # Tools menu
        #
        show_bus_monitor_action = QAction(get_icon('bus'), '&Bus Monitor', self)
        show_bus_monitor_action.setShortcut(QKeySequence('Ctrl+Shift+B'))
        show_bus_monitor_action.setStatusTip('Open bus monitor window')
        show_bus_monitor_action.triggered.connect(self._bus_monitor_manager.spawn_monitor)

        show_console_action = QAction(get_icon('terminal'), 'Interactive &Console', self)
        show_console_action.setShortcut(QKeySequence('Ctrl+Shift+T'))
        show_console_action.setStatusTip('Open interactive console window')
        show_console_action.triggered.connect(self._show_console_window)

        new_subscriber_action = QAction(get_icon('newspaper-o'), '&Subscriber', self)
        new_subscriber_action.setShortcut(QKeySequence('Ctrl+Shift+S'))
        new_subscriber_action.setStatusTip('Open subscription tool')
        new_subscriber_action.triggered.connect(
            lambda: SubscriberWindow.spawn(self, self._node, self._active_data_type_detector))

        new_plotter_action = QAction(get_icon('area-chart'), '&Plotter', self)
        new_plotter_action.setShortcut(QKeySequence('Ctrl+Shift+P'))
        new_plotter_action.setStatusTip('Open new graph plotter window')
        new_plotter_action.triggered.connect(self._plotter_manager.spawn_plotter)

        show_can_adapter_controls_action = QAction(get_icon('plug'), 'CAN &Adapter Control Panel', self)
        show_can_adapter_controls_action.setShortcut(QKeySequence('Ctrl+Shift+A'))
        show_can_adapter_controls_action.setStatusTip('Open CAN adapter control panel (if supported by the adapter)')
        show_can_adapter_controls_action.triggered.connect(self._try_spawn_can_adapter_control_panel)

        tools_menu = self.menuBar().addMenu('&Tools')
        tools_menu.addAction(show_bus_monitor_action)
        tools_menu.addAction(show_console_action)
        tools_menu.addAction(new_subscriber_action)
        tools_menu.addAction(new_plotter_action)
        tools_menu.addAction(show_can_adapter_controls_action)

        #
        # Panels menu
        #
        panels_menu = self.menuBar().addMenu('&Panels')

        for idx, panel in enumerate(PANELS):
            action = QAction(panel.name, self)
            icon = panel.get_icon()
            if icon:
                action.setIcon(icon)
            if idx < 9:
                action.setShortcut(QKeySequence('Ctrl+Shift+%d' % (idx + 1)))
            action.triggered.connect(lambda state, panel=panel: panel.safe_spawn(self, self._node))
            panels_menu.addAction(action)

        #
        # Help menu
        #
        uavcan_website_action = QAction(get_icon('globe'), 'Open UAVCAN &Website', self)
        uavcan_website_action.triggered.connect(lambda: QDesktopServices.openUrl(QUrl('http://pyuavcan_v0.org')))

        show_log_directory_action = QAction(get_icon('pencil-square-o'), 'Open &Log Directory', self)
        show_log_directory_action.triggered.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(log_file.name))))

        about_action = QAction(get_icon('info'), '&About', self)
        about_action.triggered.connect(lambda: AboutWindow(self).show())

        help_menu = self.menuBar().addMenu('&Help')
        help_menu.addAction(uavcan_website_action)
        help_menu.addAction(show_log_directory_action)
        help_menu.addAction(about_action)

        #
        # Window layout
        #
        self.statusBar().show()

        def make_vbox(*widgets, stretch_index=None):
            box = QVBoxLayout(self)
            for idx, w in enumerate(widgets):
                box.addWidget(w, 1 if idx == stretch_index else 0)
            container = QWidget(self)
            container.setLayout(box)
            container.setContentsMargins(0, 0, 0, 0)
            return container

        def make_splitter(orientation, *widgets):
            spl = QSplitter(orientation, self)
            for w in widgets:
                spl.addWidget(w)
            return spl

        self.setCentralWidget(make_splitter(Qt.Horizontal,
                                            make_vbox(self._local_node_widget,
                                                      self._node_monitor_widget,
                                                      self._file_server_widget),
                                            make_splitter(Qt.Vertical,
                                                          make_vbox(self._log_message_widget),
                                                          make_vbox(self._dynamic_node_id_allocation_widget,
                                                                    stretch_index=1))))

    def _try_spawn_can_adapter_control_panel(self):
        try:
            spawn_can_adapter_control_panel(self, self._node, self._iface_name)
        except Exception as ex:
            show_error('CAN Adapter Control Panel error', 'Could not spawn CAN Adapter Control Panel', ex, self)

    def _make_console_context(self):
        default_transfer_priority = 30

        active_handles = []

        def print_yaml(obj):
            """
            Formats the argument as YAML structure using pyuavcan_v0.to_yaml(), and prints the result into stdout.
            Use this function to print received UAVCAN structures.
            """
            if obj is None:
                return

            print(pyuavcan_v0.to_yaml(obj))

        def throw_if_anonymous():
            if self._node.is_anonymous:
                raise RuntimeError('Local node is configured in anonymous mode. '
                                   'You need to set the local node ID (see the main window) in order to be able '
                                   'to send transfers.')

        def request(payload, server_node_id, callback=None, priority=None, timeout=None):
            """
            Sends a service request to the specified node. This is a convenient wrapper over node.request().
            Args:
                payload:        Request payload of type CompoundValue, e.g. pyuavcan_v0.protocol.GetNodeInfo.Request()
                server_node_id: Node ID of the node that will receive the request.
                callback:       Response callback. Default handler will print the response to stdout in YAML format.
                priority:       Transfer priority; defaults to a very low priority.
                timeout:        Response timeout, default is set according to the UAVCAN specification.
            """
            if isinstance(payload, pyuavcan_v0.dsdl.CompoundType):
                print('Interpreting the first argument as:', payload.full_name + '.Request()')
                payload = pyuavcan_v0.TYPENAMES[payload.full_name].Request()
            throw_if_anonymous()
            priority = priority or default_transfer_priority
            callback = callback or print_yaml
            return self._node.request(payload, server_node_id, callback, priority=priority, timeout=timeout)

        def serve(uavcan_type, callback):
            """
            Registers a service server. The callback will be invoked every time the local node receives a
            service request of the specified type. The callback accepts an pyuavcan_v0.Event object
            (refer to the PyUAVCAN documentation for more info), and returns the response object.
            Example:
                >>> def serve_acs(e):
                >>>     print_yaml(e.request)
                >>>     return pyuavcan_v0.protocol.AccessCommandShell.Response()
                >>> serve(pyuavcan_v0.protocol.AccessCommandShell, serve_acs)
            Args:
                uavcan_type:    UAVCAN service type to serve requests of.
                callback:       Service callback with the business logic, see above.
            """
            if uavcan_type.kind != uavcan_type.KIND_SERVICE:
                raise RuntimeError('Expected a service type, got a different kind')

            def process_callback(e):
                try:
                    return callback(e)
                except Exception:
                    logger.error('Unhandled exception in server callback for %r, server terminated',
                                 uavcan_type, exc_info=True)
                    sub_handle.remove()

            sub_handle = self._node.add_handler(uavcan_type, process_callback)
            active_handles.append(sub_handle)
            return sub_handle

        def broadcast(payload, priority=None, interval=None, count=None, duration=None):
            """
            Broadcasts messages, either once or periodically in the background.
            Periodic broadcasting can be configured with one or multiple termination conditions; see the arguments for
            more info. Multiple termination conditions will be joined with logical OR operation.
            Example:
                # Send one message:
                >>> broadcast(pyuavcan_v0.protocol.debug.KeyValue(key='key', value=123))
                # Repeat message every 100 milliseconds for 10 seconds:
                >>> broadcast(pyuavcan_v0.protocol.NodeStatus(), interval=0.1, duration=10)
                # Send 100 messages with 10 millisecond interval:
                >>> broadcast(pyuavcan_v0.protocol.Panic(reason_text='42!'), interval=0.01, count=100)
            Args:
                payload:    UAVCAN message structure, e.g. pyuavcan_v0.protocol.debug.KeyValue(key='key', value=123)
                priority:   Transfer priority; defaults to a very low priority.
                interval:   Broadcasting interval in seconds.
                            If specified, the message will be re-published in the background with this interval.
                            If not specified (which is default), the message will be published only once.
                count:      Stop background broadcasting when this number of messages has been broadcasted.
                            By default it is not set, meaning that the periodic broadcasting will continue indefinitely,
                            unless other termination conditions are configured.
                            Setting this value without interval is not allowed.
                duration:   Stop background broadcasting after this amount of time, in seconds.
                            By default it is not set, meaning that the periodic broadcasting will continue indefinitely,
                            unless other termination conditions are configured.
                            Setting this value without interval is not allowed.
            Returns:    If periodic broadcasting is configured, this function returns a handle that implements a method
                        'remove()', which can be called to stop the background job.
                        If no periodic broadcasting is configured, this function returns nothing.
            """
            # Validating inputs
            if isinstance(payload, pyuavcan_v0.dsdl.CompoundType):
                print('Interpreting the first argument as:', payload.full_name + '()')
                payload = pyuavcan_v0.TYPENAMES[payload.full_name]()

            if (interval is None) and (duration is not None or count is not None):
                raise RuntimeError('Cannot setup background broadcaster: interval is not set')

            throw_if_anonymous()

            # Business end is here
            def do_broadcast():
                self._node.broadcast(payload, priority or default_transfer_priority)

            do_broadcast()

            if interval is not None:
                num_broadcasted = 1         # The first was broadcasted before the job was launched
                if duration is None:
                    duration = 3600 * 24 * 365 * 1000       # See you in 1000 years
                deadline = time.monotonic() + duration

                def process_next():
                    nonlocal num_broadcasted
                    try:
                        do_broadcast()
                    except Exception:
                        logger.error('Automatic broadcast failed, job cancelled', exc_info=True)
                        timer_handle.remove()
                    else:
                        num_broadcasted += 1
                        if (count is not None and num_broadcasted >= count) or (time.monotonic() >= deadline):
                            logger.info('Background publisher for %r has stopped',
                                        pyuavcan_v0.get_uavcan_data_type(payload).full_name)
                            timer_handle.remove()

                timer_handle = self._node.periodic(interval, process_next)
                active_handles.append(timer_handle)
                return timer_handle

        def subscribe(uavcan_type, callback=None, count=None, duration=None, on_end=None):
            """
            Receives specified UAVCAN messages from the bus and delivers them to the callback.
            Args:
                uavcan_type:    UAVCAN message type to listen for.
                callback:       Callback will be invoked for every received message.
                                Default callback will print the response to stdout in YAML format.
                count:          Number of messages to receive before terminating the subscription.
                                Unlimited by default.
                duration:       Amount of time, in seconds, to listen for messages before terminating the subscription.
                                Unlimited by default.
                on_end:         Callable that will be invoked when the subscription is terminated.
            Returns:    Handler with method .remove(). Calling this method will terminate the subscription.
            """
            if (count is None and duration is None) and on_end is not None:
                raise RuntimeError('on_end is set, but it will never be called because the subscription has '
                                   'no termination condition')

            if uavcan_type.kind != uavcan_type.KIND_MESSAGE:
                raise RuntimeError('Expected a message type, got a different kind')

            callback = callback or print_yaml

            def process_callback(e):
                nonlocal count
                stop_now = False
                try:
                    callback(e)
                except Exception:
                    logger.error('Unhandled exception in subscription callback for %r, subscription terminated',
                                 uavcan_type, exc_info=True)
                    stop_now = True
                else:
                    if count is not None:
                        count -= 1
                        if count <= 0:
                            stop_now = True
                if stop_now:
                    sub_handle.remove()
                    try:
                        timer_handle.remove()
                    except Exception:
                        pass
                    if on_end is not None:
                        on_end()

            def cancel_callback():
                try:
                    sub_handle.remove()
                except Exception:
                    pass
                else:
                    if on_end is not None:
                        on_end()

            sub_handle = self._node.add_handler(uavcan_type, process_callback)
            timer_handle = None
            if duration is not None:
                timer_handle = self._node.defer(duration, cancel_callback)
            active_handles.append(sub_handle)
            return sub_handle

        def periodic(period_sec, callback):
            """
            Calls the specified callback with the specified time interval.
            """
            handle = self._node.periodic(period_sec, callback)
            active_handles.append(handle)
            return handle

        def defer(delay_sec, callback):
            """
            Calls the specified callback after the specified amount of time.
            """
            handle = self._node.defer(delay_sec, callback)
            active_handles.append(handle)
            return handle

        def stop():
            """
            Stops all periodic broadcasts (see broadcast()), terminates all subscriptions (see subscribe()),
            and cancels all deferred and periodic calls (see defer(), periodic()).
            """
            for h in active_handles:
                try:
                    logger.debug('Removing handle %r', h)
                    h.remove()
                except Exception:
                    pass
            active_handles.clear()

        def can_send(can_id, data, extended=False):
            """
            Args:
                can_id:     CAN ID of the frame
                data:       Payload as bytes()
                extended:   True to send a 29-bit frame; False to send an 11-bit frame
            """
            self._node.can_driver.send(can_id, data, extended=extended)

        return [
            InternalObjectDescriptor('can_iface_name', self._iface_name,
                                     'Name of the CAN bus interface'),
            InternalObjectDescriptor('node', self._node,
                                     'UAVCAN node instance'),
            InternalObjectDescriptor('node_monitor', self._node_monitor_widget.monitor,
                                     'Object that stores information about nodes currently available on the bus'),
            InternalObjectDescriptor('request', request,
                                     'Sends UAVCAN request transfers to other nodes'),
            InternalObjectDescriptor('serve', serve,
                                     'Serves UAVCAN service requests'),
            InternalObjectDescriptor('broadcast', broadcast,
                                     'Broadcasts UAVCAN messages, once or periodically'),
            InternalObjectDescriptor('subscribe', subscribe,
                                     'Receives UAVCAN messages'),
            InternalObjectDescriptor('periodic', periodic,
                                     'Invokes a callback from the node thread with the specified time interval'),
            InternalObjectDescriptor('defer', defer,
                                     'Invokes a callback from the node thread once after the specified timeout'),
            InternalObjectDescriptor('stop', stop,
                                     'Stops all ongoing tasks of broadcast(), subscribe(), defer(), periodic()'),
            InternalObjectDescriptor('print_yaml', print_yaml,
                                     'Prints UAVCAN entities in YAML format'),
            InternalObjectDescriptor('uavcan', pyuavcan_v0,
                                     'The main Pyuavcan module'),
            InternalObjectDescriptor('main_window', self,
                                     'Main window object, holds references to all business logic objects'),
            InternalObjectDescriptor('can_send', can_send,
                                     'Sends a raw CAN frame'),
        ]

    def _show_console_window(self):
        try:
            self._console_manager.show_console_window(self)
        except Exception as ex:
            logger.error('Could not spawn console', exc_info=True)
            show_error('Console error', 'Could not spawn console window', ex, self)
            return

    def _show_node_window(self, node_id):
        if node_id in self._node_windows:
            # noinspection PyBroadException
            try:
                self._node_windows[node_id].close()
                self._node_windows[node_id].setParent(None)
                self._node_windows[node_id].deleteLater()
            except Exception:
                pass    # Sometimes fails with "wrapped C/C++ object of type NodePropertiesWindow has been deleted"
            del self._node_windows[node_id]

        w = NodePropertiesWindow(self, self._node, node_id, self._file_server_widget,
                                 self._node_monitor_widget.monitor, self._dynamic_node_id_allocation_widget)
        w.show()
        self._node_windows[node_id] = w

    def _spin_node(self):
        # We're running the node in the GUI thread.
        # This is not great, but at the moment seems like other options are even worse.
        try:
            self._node.spin(0)
            self._successive_node_errors = 0
        except Exception as ex:
            self._successive_node_errors += 1

            msg = 'Node spin error [%d of %d]: %r' % (self._successive_node_errors, self.MAX_SUCCESSIVE_NODE_ERRORS, ex)

            if self._successive_node_errors >= self.MAX_SUCCESSIVE_NODE_ERRORS:
                show_error('Node failure',
                           'Local UAVCAN node has generated too many errors and will be terminated.\n'
                           'Please restart the application.',
                           msg, self)
                self._node_spin_timer.stop()
                self._node.close()

            logger.error(msg, exc_info=True)
            self.statusBar().showMessage(msg, 3000)

    def closeEvent(self, qcloseevent):
        self._plotter_manager.close()
        self._console_manager.close()
        self._active_data_type_detector.close()
        super(MainWindow, self).closeEvent(qcloseevent)


def main():
    logger.info('Starting the application')
    app = QApplication(sys.argv)

    while True:
        # Asking the user to specify which interface to work with
        try:
            iface, iface_kwargs, dsdl_directory = run_setup_window(get_app_icon(), args.dsdl)
            if not iface:
                sys.exit(0)
        except Exception as ex:
            show_error('Fatal error', 'Could not list available interfaces', ex, blocking=True)
            sys.exit(1)

        if not dsdl_directory:
            dsdl_directory = args.dsdl

        try:
            if dsdl_directory:
                logger.info('Loading custom DSDL from %r', dsdl_directory)
                pyuavcan_v0.load_dsdl(dsdl_directory)
                logger.info('Custom DSDL loaded successfully')

                # setup an environment variable for sub-processes to know where to load custom DSDL from
                os.environ['UAVCAN_CUSTOM_DSDL_PATH'] = dsdl_directory
        except Exception as ex:
            logger.exception('No DSDL loaded from %r, only standard messages will be supported', dsdl_directory)
            show_error('DSDL not loaded',
                       'Could not load DSDL definitions from %r.\n'
                       'The application will continue to work without the custom DSDL definitions.' % dsdl_directory,
                       ex, blocking=True)

        # Trying to start the node on the specified interface
        try:
            node_info = pyuavcan_v0.protocol.GetNodeInfo.Response()
            node_info.name = NODE_NAME
            node_info.software_version.major = __version__[0]
            node_info.software_version.minor = __version__[1]

            node = pyuavcan_v0.make_node(iface,
                                    node_info=node_info,
                                    mode=pyuavcan_v0.protocol.NodeStatus().MODE_OPERATIONAL,
                                    **iface_kwargs)

            # Making sure the interface is alright
            node.spin(0.1)
        except pyuavcan_v0.transport.TransferError:
            # allow unrecognized messages on startup:
            logger.warning('UAVCAN Transfer Error occurred on startup', exc_info=True)
            break
        except Exception as ex:
            logger.error('UAVCAN node init failed', exc_info=True)
            show_error('Fatal error', 'Could not initialize UAVCAN node', ex, blocking=True)
        else:
            break

    logger.info('Creating main window; iface %r', iface)
    window = MainWindow(node, iface)
    window.show()

    try:
        update_checker.begin_async_check(window)
    except Exception:
        logger.error('Could not start update checker', exc_info=True)

    logger.info('Init complete, invoking the Qt event loop')
    exit_code = app.exec_()

    node.close()

    sys.exit(exit_code)
