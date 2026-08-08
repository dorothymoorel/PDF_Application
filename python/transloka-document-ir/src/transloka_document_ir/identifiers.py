from enum import StrEnum
from typing import Annotated
from uuid import uuid4

from pydantic import StringConstraints

_UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}"


class EntityIdPrefix(StrEnum):
    DOCUMENT = "doc_"
    PROJECT = "prj_"
    FILE = "fil_"
    SECTION = "sec_"
    PAGE = "pag_"
    BLOCK = "blk_"
    SEGMENT = "seg_"
    ASSET = "ast_"
    TABLE = "tbl_"
    CELL = "cel_"
    ANNOTATION = "ann_"
    RELATIONSHIP = "rel_"
    WARNING = "wrn_"


DocumentId = Annotated[str, StringConstraints(pattern=rf"^doc_{_UUID}$")]
ProjectId = Annotated[str, StringConstraints(pattern=rf"^prj_{_UUID}$")]
FileId = Annotated[str, StringConstraints(pattern=rf"^fil_{_UUID}$")]
SectionId = Annotated[str, StringConstraints(pattern=rf"^sec_{_UUID}$")]
PageId = Annotated[str, StringConstraints(pattern=rf"^pag_{_UUID}$")]
BlockId = Annotated[str, StringConstraints(pattern=rf"^blk_{_UUID}$")]
SegmentId = Annotated[str, StringConstraints(pattern=rf"^seg_{_UUID}$")]
AssetId = Annotated[str, StringConstraints(pattern=rf"^ast_{_UUID}$")]
TableId = Annotated[str, StringConstraints(pattern=rf"^tbl_{_UUID}$")]
CellId = Annotated[str, StringConstraints(pattern=rf"^cel_{_UUID}$")]
AnnotationId = Annotated[str, StringConstraints(pattern=rf"^ann_{_UUID}$")]
RelationshipId = Annotated[str, StringConstraints(pattern=rf"^rel_{_UUID}$")]
WarningId = Annotated[str, StringConstraints(pattern=rf"^wrn_{_UUID}$")]
EntityId = Annotated[
    str,
    StringConstraints(pattern=rf"^(?:doc|sec|pag|blk|seg|ast|tbl|cel|ann|rel|wrn)_{_UUID}$"),
]


def new_entity_id(prefix: EntityIdPrefix) -> str:
    if not isinstance(prefix, EntityIdPrefix):
        raise TypeError("Entity ID prefix must be a supported EntityIdPrefix.")
    return f"{prefix.value}{uuid4()}"
