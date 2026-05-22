"""
文件/目录结构构建

从 GitNexus gitnexus/src/core/ingestion/structure-processor.ts 改写

将文件扫描结果转换为文件/目录节点和 CONTAINS 关系。
"""

from __future__ import annotations

import hashlib
import os
from typing import Optional

from app.kg.types import (
    GraphNode, GraphRelationship,
    NODE_FILE, NODE_FOLDER, REL_CONTAINS,
    ScanResult,
)
from app.kg.graph import KnowledgeGraph


class StructureBuilder:
    """构建文件系统的树状结构

    从 GitNexus structure-processor.ts 改写
    将 ScanResult 列表转换为知识图谱中的文件和目录节点。
    """

    def build(self, scan_results: list[ScanResult],
              repo_path: str) -> KnowledgeGraph:
        """构建文件/目录结构

        Args:
            scan_results: 文件扫描结果
            repo_path: 仓库根目录（用于计算相对路径）

        Returns:
            包含文件/目录节点和 CONTAINS 关系的知识图谱
        """
        graph = KnowledgeGraph()
        repo_path = os.path.abspath(repo_path)

        # 收集所有需要的目录路径
        all_dirs: set[str] = set()
        for r in scan_results:
            dir_path = os.path.dirname(r.file_path)
            if dir_path:
                # 添加路径中的所有父目录
                parts = dir_path.replace("\\", "/").split("/")
                for i in range(len(parts)):
                    parent = "/".join(parts[:i + 1])
                    all_dirs.add(parent)

        # 添加根目录节点
        root_node_id = self._folder_id(repo_path)
        root_node = GraphNode(
            id=root_node_id,
            type=NODE_FOLDER,
            name=os.path.basename(repo_path) or repo_path,
            file_path="",
            properties={"path": repo_path, "is_root": True},
        )
        graph.add_node(root_node)

        # 添加子目录节点
        for dir_path in sorted(all_dirs):
            node_id = self._folder_id(repo_path, dir_path)
            node = GraphNode(
                id=node_id,
                type=NODE_FOLDER,
                name=os.path.basename(dir_path) or dir_path,
                file_path=dir_path,
            )
            graph.add_node(node)

            # CONTAINS 关系：父目录 → 子目录
            parent_dir = os.path.dirname(dir_path)
            if parent_dir:
                parent_id = self._folder_id(repo_path, parent_dir)
            else:
                parent_id = root_node_id

            rel_id = f"contains:{parent_id}->{node_id}"
            graph.add_relationship(GraphRelationship(
                id=rel_id,
                source_id=parent_id,
                target_id=node_id,
                type=REL_CONTAINS,
                properties={},
            ))

        # 添加文件节点
        for r in scan_results:
            node_id = self._file_id(r.file_path)
            node = GraphNode(
                id=node_id,
                type=NODE_FILE,
                name=os.path.basename(r.file_path),
                file_path=r.file_path,
                properties={
                    "size": r.size,
                    "extension": r.extension,
                    "absolute_path": r.absolute_path,
                },
            )
            graph.add_node(node)

            # CONTAINS 关系：所在目录 → 文件
            dir_path = os.path.dirname(r.file_path)
            if dir_path:
                parent_id = self._folder_id(repo_path, dir_path)
            else:
                parent_id = root_node_id

            rel_id = f"contains:{parent_id}->{node_id}"
            graph.add_relationship(GraphRelationship(
                id=rel_id,
                source_id=parent_id,
                target_id=node_id,
                type=REL_CONTAINS,
                properties={},
            ))

        return graph

    @staticmethod
    def _file_id(file_path: str) -> str:
        """生成文件节点的唯一 ID"""
        return f"file://{file_path.replace(os.sep, '/')}"

    @staticmethod
    def _folder_id(repo_path: str, dir_path: str = "") -> str:
        """生成目录节点的唯一 ID"""
        if dir_path:
            return f"folder://{dir_path.replace(os.sep, '/')}"
        return f"folder://{os.path.basename(repo_path)}"
