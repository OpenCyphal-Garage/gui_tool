#
# Copyright (C) 2016  UAVCAN Development Team  <uavcan.org>
#
# This software is distributed under the terms of the MIT License.
#
# Author: Pavel Kirienko <pavel.kirienko@zubax.com>
#

import os
import re
import sys
import json
import time
import tempfile
import threading
import urllib.request
from logging import getLogger
from PyQt5.QtWidgets import QMessageBox
from PyQt5.QtCore import QTimer
from .version import __version__


logger = getLogger(__name__)


try:
    # noinspection PyUnresolvedReferences
    sys.getwindowsversion()
    RUNNING_ON_WINDOWS = True
except AttributeError:
    RUNNING_ON_WINDOWS = False


def _version_tuple_to_int(vt):
    out = 0
    for x in vt:
        out *= 1000
        out += x
    return out


def _do_windows_check():
    import easywebdav

    hostname = 'files.zubax.com'
    directory = 'products/org.uavcan.gui_tool'
    # Some people, when confronted with a problem, think: "I know, I WON'T use regular expressions."
    # Now they have two problems.
    regex = r'(?i).*?gui.?tool.+?(\d+\.\d+).*?\.\w\w\w$'

    con = easywebdav.connect(hostname, protocol='https')
    items = con.ls(directory)
    logger.debug('Available items: %r', items)

    matches = []    # path, version tuple

    for it in items:
        if directory.strip('/') == it.name.strip('/'):
            continue
        name = it.name.split('/')[-1]
        version_match = re.match(regex, name)
        if version_match:
            version_tuple = [int(x) for x in version_match.group(1).split('.')]
            matches.append((it.name, version_tuple))

    matches = list(sorted(matches, key=lambda x: _version_tuple_to_int(x[1]), reverse=True))
    logger.debug('Matches: %r', matches)

    if len(matches) > 0:
        newest = matches[0]
        if _version_tuple_to_int(newest[1]) > _version_tuple_to_int(__version__):
            url = 'https://' + hostname + newest[0]
            return '<a href="{0}">{0}</a>'.format(url)


def _do_pip_check():
    request = urllib.request.Request('https://api.github.com/repos/UAVCAN/gui_tool/tags',
                                     headers={
                                         'Accept': 'application/vnd.github.v3+json',
                                     })
    with urllib.request.urlopen(request) as response:
        data = response.read()

    data = json.loads(data.decode('utf8'), encoding='utf8')

    newest_tag_name = data[0]['name']
    logger.debug('Newest tag: %r', newest_tag_name)

    match = re.match(r'^.*?(\d{1,3})\.(\d{1,3})', newest_tag_name)

    version_tuple = int(match.group(1)), int(match.group(2))
    logger.debug('Parsed version tuple: %r', version_tuple)

    if _version_tuple_to_int(version_tuple) > _version_tuple_to_int(__version__):
        git_url = 'https://github.com/UAVCAN/gui_tool'
        return 'pip3 install --upgrade git+<a href="{0}">{0}</a>@{1}'.format(git_url, newest_tag_name)


# noinspection PyBroadException
def _should_continue():
    min_check_interval = 3600 * 24

    update_timestamp_file = os.path.join(tempfile.gettempdir(), 'uavcan_gui_tool', 'update_check_timestamp')

    try:
        with open(update_timestamp_file, 'r') as f:
            update_check_timestamp = float(f.read().strip())
    except Exception:
        logger.debug('Update timestamp file could not be read', exc_info=True)
        update_check_timestamp = 0

    if (time.time() - update_check_timestamp) < min_check_interval:
        return False

    try:
        os.makedirs(os.path.dirname(update_timestamp_file))
    except Exception:
        pass            # Nobody cares.

    with open(update_timestamp_file, 'w') as f:
        f.write(str(time.time()))

    return True


def begin_async_check(parent):
    if not _should_continue():
        logger.info('Update check skipped')
        return

    update_reference = None

    def check_from_gui_thread():
        if background_thread.is_alive():
            logger.info('Update checker is still running...')
        else:
            gui_timer.stop()
            logger.info('Update checker stopped')

        if update_reference is None:
            return

        mbox = QMessageBox(parent)
        mbox.setWindowTitle('Update Available')
        mbox.setText('New version is available.<br><br>%s' % update_reference)
        mbox.setIcon(QMessageBox.Information)
        mbox.setStandardButtons(QMessageBox.Ok)
        mbox.exec()

    def do_background_check():
        nonlocal update_reference
        # noinspection PyBroadException
        try:
            if RUNNING_ON_WINDOWS:
                update_reference = _do_windows_check()
            else:
                update_reference = _do_pip_check()

            logger.info('Update reference: %r', update_reference)
        except Exception:
            logger.error('Update checker failed', exc_info=True)

    background_thread = threading.Thread(target=do_background_check, name='update_checker', daemon=True)
    background_thread.start()

    gui_timer = QTimer(parent)
    gui_timer.setSingleShot(False)
    gui_timer.timeout.connect(check_from_gui_thread)
    gui_timer.start(2000)
