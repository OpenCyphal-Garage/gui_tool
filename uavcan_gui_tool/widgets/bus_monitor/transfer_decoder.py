#
# Copyright (C) 2016  UAVCAN Development Team  <uavcan.org>
#
# This software is distributed under the terms of the MIT License.
#
# Author: Pavel Kirienko <pavel.kirienko@zubax.com>
#

import uavcan
from uavcan.transport import Transfer, Frame

# How many rows will be traversed while looking for beginning/end of a multi frame transfer
TABLE_TRAVERSING_RANGE = 2000


class DecodingFailedException(Exception):
    pass


def _get_transfer_id(frame):
    if len(frame.data):
        return frame.data[-1] & 0b00011111


def _is_start_of_transfer(frame):
    if len(frame.data):
        return frame.data[-1] & 0b10000000


def _is_end_of_transfer(frame):
    if len(frame.data):
        return frame.data[-1] & 0b01000000


def decode_transfer_from_frame(entry_row, row_to_frame):
    entry_frame = row_to_frame(entry_row)
    can_id = entry_frame.id
    transfer_id = _get_transfer_id(entry_frame)
    frames = [entry_frame]

    related_rows = []

    # Scanning backward looking for the first frame
    row = entry_row - 1
    while not _is_start_of_transfer(frames[0]):
        if row < 0 or entry_row - row > TABLE_TRAVERSING_RANGE:
            raise DecodingFailedException('SOF not found')
        f = row_to_frame(row)
        row -= 1
        if f.id == can_id and _get_transfer_id(f) == transfer_id:
            frames.insert(0, f)
            related_rows.insert(0, row)

    # Scanning forward looking for the last frame
    row = entry_row + 1
    while not _is_end_of_transfer(frames[-1]):
        f = row_to_frame(row)
        if f is None or row - entry_row > TABLE_TRAVERSING_RANGE:
            raise DecodingFailedException('EOF not found')
        row += 1
        if f.id == can_id and _get_transfer_id(f) == transfer_id:
            frames.append(f)
            related_rows.append(row)

    # The transfer is now fully recovered
    tr = Transfer()
    tr.from_frames([Frame(x.id, x.data) for x in frames])

    return related_rows, uavcan.to_yaml(tr.payload)
