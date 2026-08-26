"""WORKFLOW_WITH relation from co-access / sequential patterns."""

from typing import List, Optional

from src.config import Config, get_config
from src.models.file_descriptor import FileDescriptor
from src.relations.base import RelationExtractor

try:
    from prefixspan import PrefixSpan
    HAS_PREFIXSPAN = True
except ImportError:
    HAS_PREFIXSPAN = False


class WorkflowWithExtractor(RelationExtractor):
    relation_type = "WORKFLOW_WITH"

    def __init__(self, config: Optional[Config] = None, access_log: Optional[List[List[str]]] = None):
        self.config = config or get_config()
        self.access_log = access_log

    def discover(self, file_nodes: List[FileDescriptor]) -> List:
        id_by_path = {f.path: f.id for f in file_nodes}
        sequences = self.access_log or self._synthetic_sequences(file_nodes)

        if not sequences:
            return self._time_proximity_pairs(file_nodes)

        mapped = []
        for seq in sequences:
            mids = [id_by_path.get(p) or id_by_path.get(p.replace("\\", "/")) for p in seq]
            mids = [m for m in mids if m]
            if len(mids) >= 2:
                mapped.append(mids)

        if not mapped or not HAS_PREFIXSPAN:
            return self._time_proximity_pairs(file_nodes)

        ps = PrefixSpan(mapped)
        patterns = ps.frequent(minsup=2)
        edges = []
        seen = set()
        for pat, support in patterns[:50]:
            if len(pat) < 2:
                continue
            for i in range(len(pat) - 1):
                a, b = pat[i], pat[i + 1]
                key = (a, b)
                if key not in seen:
                    seen.add(key)
                    edges.append((a, b, "WORKFLOW_WITH", {"support": support}))
        return edges

    def _synthetic_sequences(self, file_nodes: List[FileDescriptor]) -> List[List[str]]:
        """Build pseudo sessions from files modified within the same window."""
        sorted_f = sorted(file_nodes, key=lambda x: x.modified_time)
        window = self.config.near_in_time_window_min * 60
        sessions: List[List[str]] = []
        session: List[str] = []
        last_t = None
        for f in sorted_f:
            if last_t is None or f.modified_time - last_t <= window:
                session.append(f.path)
            else:
                if len(session) >= 2:
                    sessions.append(session)
                session = [f.path]
            last_t = f.modified_time
        if len(session) >= 2:
            sessions.append(session)
        return sessions

    def _time_proximity_pairs(self, file_nodes: List[FileDescriptor]) -> List:
        from src.relations.near_in_time import NearInTimeExtractor
        near = NearInTimeExtractor(self.config).discover(file_nodes)
        return [
            (s, t, "WORKFLOW_WITH", {"source": "time_proxy", **props})
            for s, t, _, props in near
        ]
