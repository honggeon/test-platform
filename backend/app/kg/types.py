"""
知识图谱数据类型

从 GitNexus gitnexus/src/core/graph/types.ts 改写

定义图节点和关系的数据结构，用于代码知识图谱的构建和查询。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


# ── 节点类型常量 ──────────────────────────────────────────────────────────

# 文件系统
NODE_FILE = "file"
NODE_FOLDER = "folder"

# 代码符号
NODE_CLASS = "class"
NODE_FUNCTION = "function"
NODE_METHOD = "method"
NODE_VARIABLE = "variable"
NODE_MODULE = "module"
NODE_INTERFACE = "interface"
NODE_ENUM = "enum"
NODE_STRUCT = "struct"

# 路由 / API
NODE_ROUTE = "route"
NODE_API_ENDPOINT = "api_endpoint"

# 工具 / ORM
NODE_TOOL = "tool"
NODE_CODE_ELEMENT = "code_element"

# 图结构
NODE_COMMUNITY = "community"
NODE_PROCESS = "process"
NODE_MARKDOWN_SECTION = "markdown_section"


# ── 关系类型常量 ──────────────────────────────────────────────────────────

# 文件系统
REL_CONTAINS = "CONTAINS"           # folder → file/folder

# 导入 / 依赖
REL_IMPORTS = "IMPORTS"             # file → file (import/require)

# 调用
REL_CALLS = "CALLS"                 # caller → callee

# 继承 / 实现
REL_EXTENDS = "EXTENDS"             # class → parent_class
REL_IMPLEMENTS = "IMPLEMENTS"       # class → interface
REL_METHOD_OVERRIDES = "METHOD_OVERRIDES"  # method → overridden_method
REL_METHOD_IMPLEMENTS = "METHOD_IMPLEMENTS" # method → interface_method

# 所属关系
REL_DEFINED_IN = "DEFINED_IN"       # symbol → file (符号定义在哪个文件)
REL_MEMBER_OF = "MEMBER_OF"         # method → class, class → module

# 路由
REL_HANDLES_ROUTE = "HANDLES_ROUTE" # handler → route

# ORM
REL_QUERIES = "QUERIES"             # file → code_element (ORM model)

# 进程 / 执行流
REL_STEP_IN_PROCESS = "STEP_IN_PROCESS"  # symbol → process
REL_ENTRY_POINT_OF = "ENTRY_POINT_OF"    # route/tool → process

# Markdown
REL_LINKS_TO = "LINKS_TO"            # markdown_section → markdown_section


# ── 数据结构 ──────────────────────────────────────────────────────────────


@dataclass
class GraphNode:
    """知识图谱节点

    对应 GitNexus 的 GraphNode 类型 (gitnexus-shared)
    """
    id: str                             # 唯一标识，如 "file://src/main.py"
    type: str                           # 节点类型 (NODE_* 常量)
    name: str                           # 节点名称
    file_path: Optional[str] = None     # 源文件路径
    start_line: Optional[int] = None    # 起始行号
    end_line: Optional[int] = None      # 结束行号
    properties: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.id:
            raise ValueError("GraphNode.id is required")


@dataclass
class GraphRelationship:
    """知识图谱关系

    对应 GitNexus 的 GraphRelationship 类型
    """
    id: str                             # 唯一标识
    source_id: str                      # 源节点 ID
    target_id: str                      # 目标节点 ID
    type: str                           # 关系类型 (REL_* 常量)
    properties: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.id:
            raise ValueError("GraphRelationship.id is required")


# ── 扫描结果 ──────────────────────────────────────────────────────────────


@dataclass
class ScanResult:
    """文件扫描结果"""
    file_path: str          # 相对于仓库根目录的路径
    absolute_path: str      # 绝对路径
    size: int               # 文件大小（字节）
    extension: str          # 文件扩展名


@dataclass
class PhaseProgress:
    """管道阶段进度"""
    phase: str
    percent: int            # 0-100
    message: str = ""
