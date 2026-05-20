from .base import RelationExtractor, Edge
from .in_folder import InFolderExtractor
from .same_type import SameTypeExtractor
from .near_in_time import NearInTimeExtractor
from .has_version import HasVersionExtractor
from .depends_on import DependsOnExtractor
from .references import ReferencesExtractor
from .contains import ContainsExtractor
from .similar_to import SimilarToExtractor
from .workflow_with import WorkflowWithExtractor
from .visually_similar_to import VisuallySimilarToExtractor
from .belongs_to_project import BelongsToProjectExtractor
from .tagged_with import TaggedWithExtractor

ALL_EXTRACTORS = [
    InFolderExtractor,
    SameTypeExtractor,
    NearInTimeExtractor,
    HasVersionExtractor,
    DependsOnExtractor,
    ReferencesExtractor,
    ContainsExtractor,
    SimilarToExtractor,
    WorkflowWithExtractor,
    VisuallySimilarToExtractor,
    BelongsToProjectExtractor,
    TaggedWithExtractor,
]

__all__ = [
    "RelationExtractor",
    "Edge",
    "ALL_EXTRACTORS",
    "InFolderExtractor",
    "SameTypeExtractor",
    "NearInTimeExtractor",
    "HasVersionExtractor",
    "DependsOnExtractor",
    "ReferencesExtractor",
    "ContainsExtractor",
    "SimilarToExtractor",
    "WorkflowWithExtractor",
    "VisuallySimilarToExtractor",
    "BelongsToProjectExtractor",
    "TaggedWithExtractor",
]
