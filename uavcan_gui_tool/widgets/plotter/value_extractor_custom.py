from .value_extractor import Extractor


class customExtractor(Extractor):
    def __init__(self, data_type_name, extraction_expression, color):
        super(customExtractor, self).__init__(data_type_name, extraction_expression, [], color)

    def try_extract(self, customData):
        print("customExtrator try extract:{}".format(customData))
        print(type(customData))
        if customData.data_type_name != self.data_type_name:
            return

        return customData
