#
# Copyright (C) 2016  UAVCAN Development Team  <uavcan.org>
#
# This software is distributed under the terms of the MIT License.
#
# Author: Pavel Kirienko <pavel.kirienko@zubax.com>
#


class AbstractPlotArea:
    def add_value(self, extractor, timestamp, value):
        pass

    def remove_curves_provided_by_extractor(self, extractor):
        pass

    def clear(self):
        pass

    def update(self):
        pass
