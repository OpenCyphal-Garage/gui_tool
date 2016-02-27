#
# Copyright (C) 2016  UAVCAN Development Team  <uavcan.org>
#
# This software is distributed under the terms of the MIT License.
#
# Author: Pavel Kirienko <pavel.kirienko@zubax.com>
#

import uavcan


class UAVCANTypeInspector:
    def __init__(self, type_or_struct, mode=None):
        # noinspection PyBroadException
        try:
            self.type = uavcan.get_uavcan_data_type(type_or_struct)
        except Exception:
            self.type = type_or_struct
        self.mode = mode

        if (self.type.kind == self.type.KIND_SERVICE) == (self.mode is None):
            raise ValueError('Mode must be set for service types, and for service types only')

    def list_enum_constants(self, field_name):
        if self.mode == 'request':
            const = self.type.request_constants
        elif self.mode == 'response':
            const = self.type.response_constants
        else:
            const = self.type.constants

        prefix_len = len(field_name) + 1
        return [(x.name[prefix_len:], x) for x in const if x.name.lower().startswith(field_name.lower() + '_')]


class UAVCANStructInspector:
    def __init__(self, struct):
        if uavcan.is_request(struct):
            mode = 'request'
        elif uavcan.is_response(struct):
            mode = 'response'
        else:
            mode = None
        self.type_inspector = UAVCANTypeInspector(struct, mode)
        self.struct = struct

    def field_to_string(self, name, keep_literal=False, fallback_format=None):
        val = getattr(self.struct, name)

        # Trying prefixed constants first
        for name, const in self.type_inspector.list_enum_constants(name):
            if const.value == val:
                return ('%s (%r)' % (name, val)) if keep_literal else name

        # If the struct contains only one field
        if len(uavcan.get_fields(self.struct)) == 1:
            for name, cvalue in uavcan.get_constants(self.struct).items():
                if cvalue == val:
                    return name

        return (fallback_format or '%r') % val
