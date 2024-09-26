from enum import Enum

from discover_utils.data.annotation import DiscreteAnnotation, FreeAnnotation, ContinuousAnnotation
from discover_utils.data.data import Data
from discover_utils.data.static import Text, Image
from discover_utils.data.stream import SSIStream, Audio, Video


class Origin(Enum):
    DB = "db"  # data.handler.NovaDBHandler
    FILE = "file"  # data.handler.FileHandler
    URL = "url"  # data.handler.UrlHandler
    REQUEST = "request"

class SuperType(Enum):
    STREAM = "stream"
    ANNO = "annotation"#"anno"
    TEXT = "text"
    IMAGE = "image"
    TABLE = "table"

class SubType(Enum):
    AUDIO = "audio"
    VIDEO = "video"
    SSIStream = "ssistream"
    DISCRETE = "discrete"
    CONTINUOUS = "continuous"
    FREE = "free"

def data_description_to_string(data_desc: dict) -> str:
    """
    Convert data description to a string representation.

    Args:
        data_desc (dict): Data description dictionary.

    Returns:
        str: String representation of the data description.
    """

    id = data_desc.get("id")
    if id is not None:
        return id

    origin, super_type, sub_type, specific_type = parse_src_tag(data_desc)
    delim = "_"
    if origin == Origin.DB:
        if super_type == SuperType.ANNO:
            return delim.join(
                [data_desc["scheme"], data_desc["annotator"], data_desc["role"]]
            )
        elif super_type == SuperType.STREAM:
            return delim.join([data_desc["name"], data_desc["role"]])
        else:
            raise ValueError(f"Unknown data type {super_type} for data.")
    elif origin == Origin.FILE:
        return delim.join([data_desc["fp"]])
    else:
        raise ValueError(f"Unsupported source type {origin} for generating data description ids")


def parse_cml_filter(filter: str):
    sub_type, specific_type = None, None
    parsed = filter.split(":",2)
    super_type = SuperType(parsed[0].lower())
    if len(parsed) > 1:
        sub_type = SubType(parsed[1].lower())
    if len(parsed) > 2:
        specific_type = parsed[2].lower()
    return super_type, sub_type, specific_type

def parse_src_tag(desc):
    try:
        sub_type, specific_type = None, None
        parsed = desc["src"].split(":",3)

        if len(parsed) < 2:
            raise ValueError()
        origin = Origin(parsed[0])
        super_type = SuperType(parsed[1].lower())
        if len(parsed) > 2:
            sub_type = SubType(parsed[2].lower())
        if len(parsed) > 3:
            specific_type = parsed[3].lower()
    except:
        raise ValueError(f'Invalid value for data source {desc["src"]}')
    return origin, super_type, sub_type, specific_type

def infere_dtype(super_type: SuperType, sub_type: SubType):
    """Infers data type as specified in nova_utils.data from super_type and sub_type"""
    if super_type == SuperType.TEXT:
        return Text
    if super_type == SuperType.IMAGE:
        return Image
    if super_type == SuperType.STREAM:
        if sub_type == SubType.SSIStream:
            return SSIStream
        if super_type == SubType.AUDIO:
            return Audio
        if sub_type == SubType.VIDEO:
            return Video
    if super_type == SuperType.ANNO:
        if sub_type == SubType.DISCRETE:
            return  DiscreteAnnotation
        if sub_type == SubType.CONTINUOUS:
            return  ContinuousAnnotation
        if sub_type == SubType.FREE:
            return FreeAnnotation
    return Data