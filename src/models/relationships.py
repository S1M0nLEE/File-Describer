from __future__ import annotations

from enum import Enum


class RelationType(str, Enum):
    IN_FOLDER = "IN_FOLDER"
    SAME_TYPE = "SAME_TYPE"
    SIMILAR_TO = "SIMILAR_TO"
    HAS_VERSION = "HAS_VERSION"
    IS_PREVIOUS_VERSION_OF = "IS_PREVIOUS_VERSION_OF"
    VERSION_VARIANT = "VERSION_VARIANT"
    DEPENDS_ON = "DEPENDS_ON"
    REFERENCES = "REFERENCES"
    CONTAINS = "CONTAINS"
    NEAR_IN_TIME = "NEAR_IN_TIME"
    WORKFLOW_WITH = "WORKFLOW_WITH"
    VISUALLY_SIMILAR_TO = "VISUALLY_SIMILAR_TO"
    IS_TEMPORARY_OF = "IS_TEMPORARY_OF"
    IS_BACKUP_OF = "IS_BACKUP_OF"
    BELONGS_TO_PROJECT = "BELONGS_TO_PROJECT"
    TAGGED_WITH = "TAGGED_WITH"


RELATION_LABELS_ZH: dict[str, str] = {
    "IN_FOLDER": "位于同一文件夹",
    "SAME_TYPE": "相同文件类型",
    "SIMILAR_TO": "内容语义相似",
    "HAS_VERSION": "存在其他版本",
    "IS_PREVIOUS_VERSION_OF": "是较新版本的前一版",
    "VERSION_VARIANT": "版本格式变体",
    "DEPENDS_ON": "工程依赖",
    "REFERENCES": "文档引用",
    "CONTAINS": "包含内部文件",
    "NEAR_IN_TIME": "修改时间相近",
    "WORKFLOW_WITH": "用户常一起打开",
    "VISUALLY_SIMILAR_TO": "视觉相似",
    "NEAR_DUPLICATE": "近重复",
    "IS_TEMPORARY_OF": "是临时文件",
    "IS_BACKUP_OF": "是备份文件",
    "BELONGS_TO_PROJECT": "属于同一项目",
    "TAGGED_WITH": "用户标签",
}
