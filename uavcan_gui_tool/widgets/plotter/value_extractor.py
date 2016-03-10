#
# Copyright (C) 2016  UAVCAN Development Team  <uavcan.org>
#
# This software is distributed under the terms of the MIT License.
#
# Author: Pavel Kirienko <pavel.kirienko@zubax.com>
#


EXPRESSION_VARIABLE_FOR_MESSAGE = 'msg'
EXPRESSION_VARIABLE_FOR_SRC_NODE_ID = 'src_node_id'


class Expression:
    class EvaluationError(Exception):
        pass

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
        try:
            return eval(self._compiled, globals(), locals)
        except Exception as ex:
            raise self.EvaluationError('Failed to evaluate expression: %s' % ex) from ex


class ExtractedValue:
    def __init__(self, value, ts_mono):
        self.value = value
        self.ts_mono = ts_mono

    def __repr__(self):
        return '%.6f %r' % (self.ts_mono, self.value)

    __str__ = __repr__


class Extractor:
    def __init__(self, data_type_name, extraction_expression, filter_expressions, color):
        self.data_type_name = data_type_name
        self.extraction_expression = extraction_expression
        self.filter_expressions = filter_expressions
        self.color = color

    def __repr__(self):
        return '%r %r %r' % (self.data_type_name, self.extraction_expression.source,
                             [x.source for x in self.filter_expressions])

    def try_extract(self, tr):
        if tr.data_type_name != self.data_type_name:
            return

        evaluation_kwargs = {
            EXPRESSION_VARIABLE_FOR_MESSAGE: tr.message,
            EXPRESSION_VARIABLE_FOR_SRC_NODE_ID: tr.source_node_id,
        }

        for exp in self.filter_expressions:
            if not exp.evaluate(**evaluation_kwargs):
                return

        value = self.extraction_expression.evaluate(**evaluation_kwargs)

        return ExtractedValue(value, tr.ts_mono)
