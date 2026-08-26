"""NEAR_IN_TIME relation via sliding time window."""

import statistics
from typing import List

from src.config import Config, get_config
from src.models.file_descriptor import FileDescriptor
from src.relations.base import RelationExtractor


class NearInTimeExtractor(RelationExtractor):
    relation_type = "NEAR_IN_TIME"

    def __init__(self, config: Config | None = None):
        self.config = config or get_config()
        self.window_sec = self.config.near_in_time_window_min * 60

    def discover(self, file_nodes: List[FileDescriptor]) -> List:
        if len(file_nodes) < 2:
            return []
        sorted_files = sorted(file_nodes, key=lambda f: f.modified_time)
        edges = []
        cluster: List[FileDescriptor] = [sorted_files[0]]

        def flush_cluster(cl: List[FileDescriptor]):
            if len(cl) < 2:
                return
            center_time = statistics.mean(f.modified_time for f in cl)
            center_id = min(cl, key=lambda f: abs(f.modified_time - center_time)).id
            count = 0
            max_e = self.config.near_in_time_max_edges_per_cluster
            for f in cl:
                if f.id == center_id:
                    continue
                if count >= max_e:
                    break
                edges.append((
                    f.id, center_id, "NEAR_IN_TIME",
                    {"delta_sec": abs(f.modified_time - center_time)},
                ))
                count += 1

        for f in sorted_files[1:]:
            if f.modified_time - cluster[-1].modified_time <= self.window_sec:
                cluster.append(f)
            else:
                flush_cluster(cluster)
                cluster = [f]
        flush_cluster(cluster)
        return edges
