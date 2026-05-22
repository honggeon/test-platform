"""
符号提取器

从 GitNexus gitnexus/src/core/ingestion/parsing-processor.ts 改写

使用 Python ast 模块和正则表达式，从源代码中提取符号（类、函数、变量等）。
支持 Python、JavaScript/TypeScript 的符号提取。
"""

from __future__ import annotations

import ast
import os
import re
from dataclasses import dataclass, field
from typing import Optional

from app.kg.types import (
    GraphNode, GraphRelationship,
    NODE_CLASS, NODE_FUNCTION, NODE_METHOD, NODE_VARIABLE,
    NODE_MODULE, NODE_INTERFACE, NODE_ENUM,
    REL_DEFINED_IN, REL_CONTAINS,
)


@dataclass
class SymbolExtraction:
    """符号提取结果"""
    symbols: list[GraphNode] = field(default_factory=list)
    relationships: list[GraphRelationship] = field(default_factory=list)
    imports: list[tuple[str, str]] = field(default_factory=list)  # (module, alias)


# ── 按语言分类的符号提取器 ──────────────────────────────────────────────


class PythonSymbolExtractor:
    """Python 符号提取器

    使用 Python 标准库 ast 模块，精确提取：
    - 类 (class)
    - 函数 (function)
    - 方法 (method)
    - 模块级变量 (variable)
    - import 语句
    """

    def extract(self, file_path: str, source: str) -> SymbolExtraction:
        result = SymbolExtraction()
        try:
            tree = ast.parse(source, filename=file_path)
        except SyntaxError:
            return result

        # 模块节点
        module_name = self._module_name_from_path(file_path)
        module_id = f"module://{file_path}"
        result.symbols.append(GraphNode(
            id=module_id,
            type=NODE_MODULE,
            name=module_name,
            file_path=file_path,
            start_line=1,
            end_line=len(source.splitlines()),
        ))

        self._extract_body(tree.body, file_path, module_id, result)

        return result

    def _extract_body(
        self, body: list[ast.stmt], file_path: str,
        parent_id: Optional[str], result: SymbolExtraction,
    ):
        for node in body:
            if isinstance(node, ast.ClassDef):
                self._extract_class(node, file_path, parent_id, result)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._extract_function(node, file_path, parent_id, result)
            elif isinstance(node, ast.Assign):
                self._extract_assign(node, file_path, parent_id, result)
            elif isinstance(node, ast.AnnAssign):
                self._extract_ann_assign(node, file_path, parent_id, result)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                self._extract_import(node, result)

    def _extract_class(
        self, node: ast.ClassDef, file_path: str,
        parent_id: Optional[str], result: SymbolExtraction,
    ):
        class_id = f"class://{file_path}::{node.name}"

        # 判断是否有装饰器（可能表示它是一个接口/枚举的替代）
        node_type = NODE_CLASS
        decorator_names = {d.id for d in node.decorator_list
                          if isinstance(d, ast.Name)}

        result.symbols.append(GraphNode(
            id=class_id,
            type=node_type,
            name=node.name,
            file_path=file_path,
            start_line=node.lineno,
            end_line=self._get_end_line(node),
            properties={
                "doc": ast.get_docstring(node) or "",
                "decorators": list(decorator_names),
            },
        ))

        # DEFINED_IN 关系
        if parent_id:
            result.relationships.append(GraphRelationship(
                id=f"defined_in:{class_id}->{parent_id}",
                source_id=class_id,
                target_id=parent_id,
                type=REL_DEFINED_IN,
            ))

        # 提取类内的方法和属性
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._extract_method(item, file_path, class_id, result)

    def _extract_function(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef,
        file_path: str, parent_id: Optional[str], result: SymbolExtraction,
    ):
        func_id = f"func://{file_path}::{node.name}"
        is_async = isinstance(node, ast.AsyncFunctionDef)

        result.symbols.append(GraphNode(
            id=func_id,
            type=NODE_FUNCTION,
            name=node.name,
            file_path=file_path,
            start_line=node.lineno,
            end_line=self._get_end_line(node),
            properties={
                "async": is_async,
                "doc": ast.get_docstring(node) or "",
                "decorators": [d.id for d in node.decorator_list
                              if isinstance(d, ast.Name)],
                "returns": self._format_annotation(node.returns),
            },
        ))

        if parent_id:
            result.relationships.append(GraphRelationship(
                id=f"defined_in:{func_id}->{parent_id}",
                source_id=func_id,
                target_id=parent_id,
                type=REL_DEFINED_IN,
            ))

    def _extract_method(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef,
        file_path: str, parent_id: str, result: SymbolExtraction,
    ):
        method_id = f"method://{file_path}::{parent_id.split('::')[-1]}.{node.name}"
        is_async = isinstance(node, ast.AsyncFunctionDef)

        result.symbols.append(GraphNode(
            id=method_id,
            type=NODE_METHOD,
            name=node.name,
            file_path=file_path,
            start_line=node.lineno,
            end_line=self._get_end_line(node),
            properties={
                "async": is_async,
                "doc": ast.get_docstring(node) or "",
                "decorators": [d.id for d in node.decorator_list
                              if isinstance(d, ast.Name)],
                "class_name": parent_id.split("::")[-1],
                "returns": self._format_annotation(node.returns),
            },
        ))

        # DEFINED_IN → class
        result.relationships.append(GraphRelationship(
            id=f"defined_in:{method_id}->{parent_id}",
            source_id=method_id,
            target_id=parent_id,
            type=REL_DEFINED_IN,
        ))

        # CONTAINS → class (method is part of class)
        if parent_id:
            result.relationships.append(GraphRelationship(
                id=f"contains:{parent_id}->{method_id}",
                source_id=parent_id,
                target_id=method_id,
                type=REL_CONTAINS,
            ))

    def _extract_assign(
        self, node: ast.Assign, file_path: str,
        parent_id: Optional[str], result: SymbolExtraction,
    ):
        for target in node.targets:
            if isinstance(target, ast.Name):
                var_id = f"var://{file_path}::{target.id}"
                result.symbols.append(GraphNode(
                    id=var_id,
                    type=NODE_VARIABLE,
                    name=target.id,
                    file_path=file_path,
                    start_line=node.lineno,
                    end_line=self._get_end_line(node),
                ))
                if parent_id:
                    result.relationships.append(GraphRelationship(
                        id=f"defined_in:{var_id}->{parent_id}",
                        source_id=var_id,
                        target_id=parent_id,
                        type=REL_DEFINED_IN,
                    ))

    def _extract_ann_assign(
        self, node: ast.AnnAssign, file_path: str,
        parent_id: Optional[str], result: SymbolExtraction,
    ):
        if isinstance(node.target, ast.Name):
            var_id = f"var://{file_path}::{node.target.id}"
            result.symbols.append(GraphNode(
                id=var_id,
                type=NODE_VARIABLE,
                name=node.target.id,
                file_path=file_path,
                start_line=node.lineno,
                end_line=self._get_end_line(node),
                properties={
                    "annotation": ast.dump(node.annotation) if node.annotation else "",
                },
            ))
            if parent_id:
                result.relationships.append(GraphRelationship(
                    id=f"defined_in:{var_id}->{parent_id}",
                    source_id=var_id,
                    target_id=parent_id,
                    type=REL_DEFINED_IN,
                ))

    def _extract_import(
        self, node: ast.Import | ast.ImportFrom, result: SymbolExtraction,
    ):
        if isinstance(node, ast.Import):
            for alias in node.names:
                result.imports.append((alias.name, alias.asname or alias.name))
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                # 修复: 只提取模块名，不拼接导入的符号名
                # 之前: full_name = f"{module}.{alias.name}" 导致 Resolver 找不到文件
                # 例如 from app.kg.types import REL_CALLS → module="app.kg.types" (正确)
                # 而不是 module="app.kg.types.REL_CALLS" (错误，找不到文件)
                result.imports.append((module, alias.asname or alias.name))

    @staticmethod
    def _module_name_from_path(file_path: str) -> str:
        """从文件路径提取模块名"""
        name = file_path.replace(os.sep, "/")
        if name.endswith(".py"):
            name = name[:-3]
        elif name.endswith(".pyi"):
            name = name[:-4]
        # 转换为点号分隔
        name = name.replace("/", ".")
        name = name.replace("__init__", "")
        name = name.strip(".")
        return name or "__main__"

    @staticmethod
    def _format_annotation(ann: ast.expr | None) -> str:
        """将 AST 类型注解格式化为可读的字符串"""
        if ann is None:
            return ""
        try:
            return ast.unparse(ann)
        except Exception:
            return ""

    @staticmethod
    def _get_end_line(node: ast.AST) -> int:
        """获取 AST 节点的结束行号"""
        if hasattr(node, 'end_lineno') and node.end_lineno is not None:
            return node.end_lineno
        return node.lineno


# ── JS/TS 符号提取器（基于正则）────────────────────────────────────────


class JavaScriptExtractor:
    """JavaScript/TypeScript 符号提取器

    使用正则表达式提取基本符号（类、函数、接口、变量导入导出等）。
    不支持 JSX/TSX 细节，只提取声明级别的符号。
    """

    # 类声明
    _CLASS_PATTERN = re.compile(
        r'(?:export\s+)?(?:abstract\s+)?class\s+(\w+)'
        r'(?:\s+extends\s+(\w+))?(?:\s+implements\s+[\w,\s<>,]+)?\s*\{',
        re.MULTILINE,
    )
    # 接口声明
    _INTERFACE_PATTERN = re.compile(
        r'(?:export\s+)?interface\s+(\w+)(?:\s+extends\s+[\w,\s<>]+)?\s*\{',
        re.MULTILINE,
    )
    # 函数声明（非方法）
    _FUNCTION_PATTERN = re.compile(
        r'(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(',
        re.MULTILINE,
    )
    # 箭头函数常量
    _ARROW_FUNCTION_PATTERN = re.compile(
        r'(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\([^)]*\)\s*(?::\s*\w+)?\s*=>',
        re.MULTILINE,
    )
    # 枚举
    _ENUM_PATTERN = re.compile(
        r'(?:export\s+)?(?:const\s+)?enum\s+(\w+)\s*\{',
        re.MULTILINE,
    )
    # import 语句
    _IMPORT_PATTERN = re.compile(
        r'(?:import\s+(?:\{[^}]*\}|\w+(?:\s*,\s*\{[^}]*\})?)\s+from\s+[\'"]([^\'"]+)[\'"])'
        r'|(?:import\s+[\'"]([^\'"]+)[\'"])',
        re.MULTILINE,
    )
    # require 语句
    _REQUIRE_PATTERN = re.compile(
        r'(?:const|let|var)\s+\w+\s*=\s*require\s*\(\s*[\'"]([^\'"]+)[\'"]\s*\)',
        re.MULTILINE,
    )

    def extract(self, file_path: str, source: str) -> SymbolExtraction:
        result = SymbolExtraction()

        # 模块节点
        module_id = f"module://{file_path}"
        lines = source.splitlines()
        result.symbols.append(GraphNode(
            id=module_id,
            type=NODE_MODULE,
            name=os.path.basename(file_path),
            file_path=file_path,
            start_line=1,
            end_line=len(lines),
        ))

        # 提取类
        for match in self._CLASS_PATTERN.finditer(source):
            name = match.group(1)
            start_line = source[:match.start()].count('\n') + 1
            end_line = self._find_block_end(source, match.end())
            class_id = f"class://{file_path}::{name}"
            result.symbols.append(GraphNode(
                id=class_id,
                type=NODE_CLASS,
                name=name,
                file_path=file_path,
                start_line=start_line,
                end_line=end_line,
            ))
            result.relationships.append(GraphRelationship(
                id=f"defined_in:{class_id}->{module_id}",
                source_id=class_id, target_id=module_id,
                type=REL_DEFINED_IN,
            ))

        # 提取接口
        for match in self._INTERFACE_PATTERN.finditer(source):
            name = match.group(1)
            start_line = source[:match.start()].count('\n') + 1
            end_line = self._find_block_end(source, match.end())
            iface_id = f"interface://{file_path}::{name}"
            result.symbols.append(GraphNode(
                id=iface_id,
                type=NODE_INTERFACE,
                name=name,
                file_path=file_path,
                start_line=start_line,
                end_line=end_line,
            ))
            result.relationships.append(GraphRelationship(
                id=f"defined_in:{iface_id}->{module_id}",
                source_id=iface_id, target_id=module_id,
                type=REL_DEFINED_IN,
            ))

        # 提取函数
        for match in self._FUNCTION_PATTERN.finditer(source):
            name = match.group(1)
            start_line = source[:match.start()].count('\n') + 1
            end_line = self._find_block_end(source, match.end())
            func_id = f"func://{file_path}::{name}"
            result.symbols.append(GraphNode(
                id=func_id,
                type=NODE_FUNCTION,
                name=name,
                file_path=file_path,
                start_line=start_line,
                end_line=end_line,
            ))
            result.relationships.append(GraphRelationship(
                id=f"defined_in:{func_id}->{module_id}",
                source_id=func_id, target_id=module_id,
                type=REL_DEFINED_IN,
            ))

        # 提取箭头函数常量
        for match in self._ARROW_FUNCTION_PATTERN.finditer(source):
            name = match.group(1)
            start_line = source[:match.start()].count('\n') + 1
            func_id = f"func://{file_path}::{name}"
            result.symbols.append(GraphNode(
                id=func_id,
                type=NODE_FUNCTION,
                name=name,
                file_path=file_path,
                start_line=start_line,
                end_line=start_line + 1,
                properties={"arrow": True},
            ))
            result.relationships.append(GraphRelationship(
                id=f"defined_in:{func_id}->{module_id}",
                source_id=func_id, target_id=module_id,
                type=REL_DEFINED_IN,
            ))

        # 提取枚举
        for match in self._ENUM_PATTERN.finditer(source):
            name = match.group(1)
            start_line = source[:match.start()].count('\n') + 1
            enum_id = f"enum://{file_path}::{name}"
            result.symbols.append(GraphNode(
                id=enum_id,
                type=NODE_ENUM,
                name=name,
                file_path=file_path,
                start_line=start_line,
                end_line=self._find_block_end(source, match.end()),
            ))
            result.relationships.append(GraphRelationship(
                id=f"defined_in:{enum_id}->{module_id}",
                source_id=enum_id, target_id=module_id,
                type=REL_DEFINED_IN,
            ))

        # 提取 import
        for match in self._IMPORT_PATTERN.finditer(source):
            module = match.group(1) or match.group(2)
            if module:
                result.imports.append((module, module.split("/")[-1]))

        for match in self._REQUIRE_PATTERN.finditer(source):
            module = match.group(1)
            if module:
                result.imports.append((module, module.split("/")[-1]))

        return result

    @staticmethod
    def _find_block_end(source: str, open_brace_pos: int) -> int:
        """从开放大括号位置找到匹配的闭合大括号行号"""
        depth = 0
        in_block = False
        for i, ch in enumerate(source[open_brace_pos:], start=open_brace_pos):
            if ch == '{':
                depth += 1
                in_block = True
            elif ch == '}':
                depth -= 1
                if in_block and depth == 0:
                    return source[:i + 1].count('\n') + 1
        return source.count('\n') + 1


# ── 统一调度器 ─────────────────────────────────────────────────────────────


class SymbolExtractor:
    """统一符号提取器

    根据文件扩展名选择合适的提取器。
    """

    def __init__(self):
        self._py_extractor = PythonSymbolExtractor()
        self._js_extractor = JavaScriptExtractor()

    def extract(self, file_path: str, source: str) -> SymbolExtraction:
        ext = os.path.splitext(file_path)[1].lower()

        if ext in (".py", ".pyi", ".pyx"):
            return self._py_extractor.extract(file_path, source)
        elif ext in (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts"):
            return self._js_extractor.extract(file_path, source)
        else:
            # 其他语言返回空
            return SymbolExtraction()
