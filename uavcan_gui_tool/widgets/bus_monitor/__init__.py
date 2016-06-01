#
# Copyright (C) 2016  UAVCAN Development Team  <uavcan.org>
#
# This software is distributed under the terms of the MIT License.
#
# Author: Pavel Kirienko <pavel.kirienko@zubax.com>
#

import os
import sys
import queue
import logging
import multiprocessing
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QTimer
from .window import BusMonitorWindow

logger = logging.getLogger(__name__)

try:
    # noinspection PyUnresolvedReferences
    sys.getwindowsversion()
    RUNNING_ON_WINDOWS = True
except AttributeError:
    RUNNING_ON_WINDOWS = False
    PARENT_PID = os.getppid()


class IPCChannel:
    """
    This class is built as an abstraction over the underlying IPC communication channel.
    """
    def __init__(self):
        # Queue is slower than pipe, but it allows to implement non-blocking sending easier,
        # and the buffer can be arbitrarily large.
        self._q = multiprocessing.Queue()

    def send_nonblocking(self, obj):
        try:
            self._q.put_nowait(obj)
        except queue.Full:
            pass

    def receive_nonblocking(self):
        """Returns: (True, object) if successful, (False, None) if no data to read """
        try:
            return True, self._q.get_nowait()
        except queue.Empty:
            return False, None


IPC_COMMAND_STOP = 'stop'


def _process_entry_point(channel, iface_name):
    logger.info('Bus monitor process started with PID %r', os.getpid())
    app = QApplication(sys.argv)    # Inheriting args from the parent process

    def exit_if_should():
        if RUNNING_ON_WINDOWS:
            return False
        else:
            return os.getppid() != PARENT_PID       # Parent is dead

    exit_check_timer = QTimer()
    exit_check_timer.setSingleShot(False)
    exit_check_timer.timeout.connect(exit_if_should)
    exit_check_timer.start(2000)

    def get_frame():
        received, obj = channel.receive_nonblocking()
        if received:
            if obj == IPC_COMMAND_STOP:
                logger.info('Bus monitor process has received a stop request, goodbye')
                app.exit(0)
            else:
                return obj

    win = BusMonitorWindow(get_frame, iface_name)
    win.show()

    logger.info('Bus monitor process %r initialized successfully, now starting the event loop', os.getpid())
    sys.exit(app.exec_())


# TODO: Duplicates PlotterManager; refactor into an abstract process factory
class BusMonitorManager:
    def __init__(self, node, can_iface_name):
        self._node = node
        self._can_iface_name = can_iface_name
        self._inferiors = []    # process object, channel
        self._hook_handle = None

    def _frame_hook(self, direction, frame):
        for proc, channel in self._inferiors[:]:
            if proc.is_alive():
                try:
                    channel.send_nonblocking((direction, frame))
                except Exception:
                    logger.error('Failed to send data to process %r', proc, exc_info=True)
            else:
                logger.info('Bus monitor process %r appears to be dead, removing', proc)
                self._inferiors.remove((proc, channel))

    def spawn_monitor(self):
        channel = IPCChannel()

        if self._hook_handle is None:
            self._hook_handle = self._node.can_driver.add_io_hook(self._frame_hook)

        proc = multiprocessing.Process(target=_process_entry_point, name='bus_monitor',
                                       args=(channel, self._can_iface_name))
        proc.daemon = True
        proc.start()

        self._inferiors.append((proc, channel))

        logger.info('Spawned new bus monitor process %r', proc)

    def close(self):
        try:
            self._hook_handle.remove()
        except Exception:
            pass

        for _, channel in self._inferiors:
            try:
                channel.send_nonblocking(IPC_COMMAND_STOP)
            except Exception:
                pass

        for proc, _ in self._inferiors:
            try:
                proc.join(1)
            except Exception:
                pass

        for proc, _ in self._inferiors:
            try:
                proc.terminate()
            except Exception:
                pass
