#
# Copyright (C) 2016  UAVCAN Development Team  <uavcan.org>
#
# This software is distributed under the terms of the MIT License.
#
# Author: Pavel Kirienko <pavel.kirienko@zubax.com>
#

from PyQt5.QtWidgets import QProgressDialog, QMessageBox
from . import slcan_cli


def spawn_window(parent, node, iface_name):
    driver = node.can_driver

    if not slcan_cli.CLIInterface.is_backend_supported(driver):
        mbox = QMessageBox(parent)
        mbox.setWindowTitle('Unsupported CAN Backend')
        mbox.setText('CAN Adapter Control Panel cannot be used with the current CAN backend.')
        mbox.setInformativeText('The current backend is %r.' % type(driver).__name__)
        mbox.setIcon(QMessageBox.Information)
        mbox.setStandardButtons(QMessageBox.Ok)
        mbox.show()     # Not exec() because we don't want it to block!
        return

    progress_dialog = QProgressDialog(parent)
    progress_dialog.setWindowTitle('CAN Adapter Control Panel Initialization')
    progress_dialog.setLabelText('Detecting CAN adapter capabilities...')
    progress_dialog.setMinimumDuration(800)
    progress_dialog.setCancelButton(None)
    progress_dialog.setRange(0, 0)
    progress_dialog.show()

    def supported_callback(supported):
        progress_dialog.close()

        if not supported:
            mbox = QMessageBox(parent)
            mbox.setWindowTitle('Incompatible CAN Adapter')
            mbox.setText('CAN Adapter Control Panel cannot be used with the connected adapter.')
            mbox.setInformativeText('Connected SLCAN adapter does not support CLI extensions.')
            mbox.setIcon(QMessageBox.Information)
            mbox.setStandardButtons(QMessageBox.Ok)
            mbox.show()     # Not exec() because we don't want it to block!
            return

        slcp = slcan_cli.ControlPanelWindow(parent, slcan_iface, iface_name)
        slcp.show()

    slcan_iface = slcan_cli.CLIInterface(driver)
    slcan_iface.check_is_interface_supported(supported_callback)
