#
# Copyright (C) 2016  UAVCAN Development Team  <uavcan.org>
#
# This software is distributed under the terms of the MIT License.
#
# Author: Pavel Kirienko <pavel.kirienko@zubax.com>
#


class Expression:
    def __init__(self, source=None):
        self._source = None
        self._compiled = None
        self.set(source)

    def set(self, source):
        code = compile(str(source), '<custom-expression>', 'eval')  # May throw
        self._source = source
        self._compiled = code

    @property
    def source(self):
        return self._source

    # noinspection PyShadowingBuiltins
    def evaluate(self, **locals):
        return eval(self._compiled, globals(), locals)


class NodeIDFilter:
    def __init__(self, node_id):
        self.node_id = node_id

    def match(self, tr):
        return tr.source_node_id == self.node_id


class FieldFilter:
    def __init__(self, target_field, expression):
        self.target_field = target_field
        self.expression = expression

    def match(self, tr):
        return self.expression.evaluate(msg=tr.message)


class ExtractedValue:
    def __init__(self, value, ts_mono):
        self.value = value
        self.ts_mono = ts_mono

    def __repr__(self):
        return '%.6f %r' % (self.ts_mono, self.value)

    __str__ = __repr__


class Extractor:
    def __init__(self, data_type_name, expression, filters, color):
        self.data_type_name = data_type_name
        self.expression = expression
        self.filters = filters
        self.color = color

    def try_extract(self, tr):
        if tr.data_type_name != self.data_type_name:
            return

        for fil in self.filters:
            if not fil.match(tr):
                return

        value = self.expression.evaluate(msg=tr.message)

        return ExtractedValue(value, tr.ts_mono)
