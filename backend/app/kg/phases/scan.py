"""
文件扫描

从 GitNexus gitnexus/src/core/ingestion/filesystem-walker.ts 改写

扫描代码仓库的文件树，过滤 .gitignore 匹配的文件，返回文件元信息。
"""

from __future__ import annotations

import os
import pathspec
from typing import Optional

from app.kg.types import ScanResult


# 默认忽略的目录和文件（即使不在 .gitignore 中）
DEFAULT_IGNORE_DIRS = {
    ".git", ".gitnexus", ".hg", ".svn",
    "__pycache__", ".venv", "venv", "env", ".env",
    "node_modules", "bower_components",
    ".next", ".nuxt", "dist", "build", "target",
    ".idea", ".vscode", ".vs",
    ".tox", ".eggs", "*.egg-info",
    ".mypy_cache", ".pytest_cache", ".ruff_cache",
    ".yarn", ".pnp.*",
    "coverage", ".coverage",
}

# 默认忽略的文件扩展名（二进制文件等）
DEFAULT_IGNORE_EXTS = {
    ".pyc", ".pyo", ".pyd",
    ".so", ".dll", ".dylib",
    ".exe", ".bin", ".obj", ".o", ".a", ".lib",
    ".class", ".jar",
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg",
    ".woff", ".woff2", ".ttf", ".eot",
    ".mp3", ".mp4", ".avi", ".mov",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx",
    ".zip", ".tar", ".gz", ".bz2", ".7z", ".rar",
    ".min.js", ".min.css",
    ".map",  # source maps
    ".log",
    ".lock",  # package-lock.json etc (keep only if needed)
}

# 可分析的文件扩展名（按语言分组）
ANALYZABLE_EXTS = {
    # Python
    ".py", ".pyi", ".pyx",
    # JavaScript / TypeScript
    ".js", ".jsx", ".mjs", ".cjs",
    ".ts", ".tsx", ".mts", ".cts",
    # Java
    ".java", ".kt", ".kts", ".groovy",
    # Go
    ".go",
    # Rust
    ".rs",
    # C / C++
    ".c", ".h", ".cpp", ".hpp", ".cc", ".cxx", ".hh",
    # Ruby
    ".rb",
    # PHP
    ".php",
    # Swift
    ".swift",
    # Shell
    ".sh", ".bash", ".zsh",
    # Web
    ".html", ".htm", ".css", ".scss", ".less",
    # Config / Docs
    ".yaml", ".yml", ".json", ".xml", ".toml", ".ini", ".cfg",
    ".md", ".mdx", ".rst", ".txt",
    ".sql",
    # Docker
    "Dockerfile",  # 无扩展名
    # Makefile
    "Makefile",
    ".gradle",
    ".sbt",
}


class FilesystemWalker:
    """文件系统遍历器

    从 GitNexus filesystem-walker.ts 改写
    负责扫描代码仓库，返回文件元信息列表。
    """

    def __init__(self, max_file_size: int = 1024 * 1024):  # 默认 1MB
        self.max_file_size = max_file_size
        self._ignore_spec: Optional[pathspec.PathSpec] = None

    def _load_gitignore(self, repo_path: str) -> pathspec.PathSpec:
        """加载 .gitignore 规则"""
        patterns = []
        gitignore_path = os.path.join(repo_path, ".gitignore")
        try:
            with open(gitignore_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        patterns.append(line)
        except (FileNotFoundError, IOError):
            pass
        return pathspec.PathSpec.from_lines("gitwildmatch", patterns)

    def _should_ignore(self, rel_path: str, is_dir: bool) -> bool:
        """检查路径是否应被忽略"""
        parts = rel_path.replace("\\", "/").split("/")

        # 检查目录名
        if is_dir:
            for part in parts:
                if part in DEFAULT_IGNORE_DIRS:
                    return True
        else:
            # 检查文件名
            for part in parts[:-1]:
                if part in DEFAULT_IGNORE_DIRS:
                    return True

        # 检查扩展名
        _, ext = os.path.splitext(rel_path)
        if ext.lower() in DEFAULT_IGNORE_EXTS:
            return True

        # 检查 .gitignore
        if self._ignore_spec and self._ignore_spec.match_file(rel_path):
            return True

        return False

    def walk(self, repo_path: str) -> list[ScanResult]:
        """扫描仓库，返回可分析的文件列表

        Args:
            repo_path: 仓库根目录的绝对路径

        Returns:
            ScanResult 列表
        """
        repo_path = os.path.abspath(repo_path)
        self._ignore_spec = self._load_gitignore(repo_path)

        results: list[ScanResult] = []
        errors: list[str] = []

        for root, dirs, files in os.walk(repo_path, topdown=True):
            # 计算相对路径
            rel_root = os.path.relpath(root, repo_path)
            if rel_root == ".":
                rel_root = ""

            # 过滤目录（原地修改 dirs 以控制 os.walk 的行为）
            filtered_dirs = []
            for d in dirs:
                rel_dir = f"{rel_root}/{d}" if rel_root else d
                if self._should_ignore(rel_dir, is_dir=True):
                    continue
                filtered_dirs.append(d)
            dirs[:] = filtered_dirs

            # 扫描文件
            for f in files:
                rel_file = f"{rel_root}/{f}" if rel_root else f
                if self._should_ignore(rel_file, is_dir=False):
                    continue

                abs_path = os.path.join(root, f)

                # 跳过过大的文件
                try:
                    size = os.path.getsize(abs_path)
                except OSError:
                    continue

                if size > self.max_file_size:
                    continue

                _, ext = os.path.splitext(f)
                ext = ext.lower()

                results.append(ScanResult(
                    file_path=rel_file,
                    absolute_path=abs_path,
                    size=size,
                    extension=ext,
                ))

        # 按路径排序
        results.sort(key=lambda r: r.file_path)

        return results

    @staticmethod
    def is_analyzable(extension: str) -> bool:
        """检查扩展名是否可分析"""
        return extension in ANALYZABLE_EXTS
