"""
多仓库组支持（骨架 — P2 完整实现）

需求背景：
- 微服务架构下，一个平台包含多个仓库（api-gateway, user-service, order-service）
- 需要跨仓库分析服务间依赖和影响

核心概念：
- Group: 一组相关的仓库
- Contract: 服务间 API 契约（OpenAPI/gRPC proto）
- CrossImpact: 修改 A 仓库的 API → 影响 B 仓库的消费者

配置示例 (backend/groups.yaml):
    groups:
      microservice-platform:
        repos:
          api-gateway: /path/to/api-gateway
          user-service: /path/to/user-service
        contracts: api-gateway/contracts.yaml

当前状态：骨架设计，核心逻辑待实现
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class RepoConfig:
    """仓库配置"""
    name: str
    path: str
    branch: str = "main"


@dataclass
class GroupConfig:
    """仓库组配置"""
    name: str
    repos: list[RepoConfig] = field(default_factory=list)
    contracts_path: Optional[str] = None


@dataclass
class CrossImpact:
    """跨仓库影响"""
    source_repo: str
    source_symbol: str
    target_repo: str
    target_symbol: str
    impact_type: str  # api_call / event_publish / shared_schema
    confidence: str  # high / medium / low


class GroupManager:
    """仓库组管理器

    TODO: 当前为骨架，需扩展以下能力：
    1. 解析 groups.yaml 配置
    2. 对每个仓库独立运行 pipeline
    3. 解析契约文件（OpenAPI / gRPC proto）建立跨仓库链接
    4. 跨仓库影响分析
    """

    def __init__(self, config_path: str = "backend/groups.yaml"):
        self.config_path = Path(config_path)
        self.groups: list[GroupConfig] = []

    def load_config(self) -> list[GroupConfig]:
        """加载仓库组配置"""
        if not self.config_path.exists():
            return []

        with open(self.config_path, "r") as f:
            data = yaml.safe_load(f)

        groups = []
        for name, cfg in data.get("groups", {}).items():
            repos = [
                RepoConfig(name=n, path=p)
                for n, p in cfg.get("repos", {}).items()
            ]
            groups.append(GroupConfig(
                name=name,
                repos=repos,
                contracts_path=cfg.get("contracts"),
            ))

        self.groups = groups
        return groups

    def analyze_group(self, group_name: str) -> dict:
        """分析整个仓库组

        TODO: 实现步骤：
        1. 对组内每个仓库运行 pipeline
        2. 解析契约文件，建立 CONTRACT 关系
        3. 构建跨仓库调用图
        4. 生成组级影响分析报告
        """
        raise NotImplementedError(
            "多仓库组分析尚未实现。当前请对每个仓库单独运行: "
            "python -m app.kg.cli analyze <repo_path>"
        )

    def cross_impact(
        self, group_name: str, symbol_name: str,
    ) -> list[CrossImpact]:
        """分析某符号的跨仓库影响

        TODO: 实现步骤：
        1. 找到符号所在的仓库
        2. 检查该符号是否是公共 API（在契约中暴露）
        3. 查找其他仓库中引用该 API 的代码
        4. 返回影响链
        """
        raise NotImplementedError(
            "跨仓库影响分析尚未实现"
        )
