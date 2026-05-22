"""
调用关系分析器

从 GitNexus gitnexus/src/core/ingestion/call-processor.ts 改写

分析函数/方法内部的调用语句，提取 CALLS 关系。
支持 Python ast 分析和 JS/TS 正则分析。

修复记录：
- _get_enclosing_class: 使用父节点映射替代错误的 ast.iter_child_nodes
- _get_node_id: 根据父节点映射正确区分 func:// 和 method://
- 跨文件调用: 利用 import 信息尝试解析模块别名
"""

from __future__ import annotations

import ast
import os
import re
from dataclasses import dataclass, field
from typing import Optional

from app.kg.types import (
    GraphNode,
    REL_CALLS, NODE_FUNCTION, NODE_METHOD,
)
from app.kg.graph import KnowledgeGraph


@dataclass
class CallInfo:
    """函数调用信息"""
    caller_id: str          # 调用者节点 ID
    callee_name: str        # 被调用函数名
    callee_scope: str = ""  # scope 限定（self, cls, 类名, 模块名等）
    line: int = 0           # 调用行号
    resolved: bool = False  # 是否已解析到图中的节点


class PythonCallAnalyzer:
    """Python 调用分析器

    使用 ast 遍历函数体，提取函数调用并尝试解析到已知符号。
    """

    def analyze_file(
        self, file_path: str, source: str, graph: KnowledgeGraph,
    ) -> list[tuple[str, str, str, str]]:
        """分析文件的调用关系

        Returns:
            (caller_id, callee_id, call_site_info, confidence) 列表
        """
        try:
            tree = ast.parse(source, filename=file_path)
        except SyntaxError:
            return []

        calls: list[tuple[str, str, str, str]] = []

        # 预先建立父节点映射
        parent_map = self._build_parent_map(tree)

        # 收集当前文件中的所有符号（用于调用解析）
        file_symbols = self._get_file_symbols(file_path, graph)

        # 构建 import 映射: 符号名 → target_file_path（用于跨文件调用解析）
        import_map = self._build_import_map(file_path, graph, source)

        # 构建同文件变量类型映射: var_name → class_name 或 target_file::ClassName
        # 例如: obj = Foo() → {"obj": "Foo"}
        #       obj = ImportedClass() → {"obj": "other/file.py::ImportedClass"}
        local_type_map = self._build_local_type_map(tree, import_map)

        # 遍历所有函数和方法
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                caller_id = self._get_node_id(file_path, node, parent_map)
                # 在这个函数体内查找调用
                calls.extend(self._analyze_body(
                    node, file_path, caller_id, file_symbols, graph, parent_map, import_map, local_type_map,
                ))

        return calls

    @staticmethod
    def _build_parent_map(tree: ast.AST) -> dict[ast.AST, ast.AST]:
        """建立子节点 -> 父节点映射"""
        parent_map = {}
        for parent in ast.walk(tree):
            for child in ast.iter_child_nodes(parent):
                parent_map[child] = parent
        return parent_map

    def _analyze_body(
        self, body_node: ast.AST, file_path: str,
        caller_id: str, file_symbols: dict, graph: KnowledgeGraph,
        parent_map: dict[ast.AST, ast.AST],
        import_map: dict[str, str],
        local_type_map: dict[str, str],
    ) -> list[tuple[str, str, str, str]]:
        """分析函数体中的调用"""
        results = []

        # 确定封闭类名
        enclosing_class = self._get_enclosing_class(body_node, parent_map)

        for node in ast.walk(body_node):
            if not isinstance(node, ast.Call):
                continue

            call_info = self._extract_call_info(node, file_path)

            if call_info is None:
                continue

            call_info.caller_id = caller_id
            call_info.line = getattr(node, 'lineno', 0)

            # 尝试解析调用
            resolved = self._resolve_call(call_info, file_symbols, graph,
                                           enclosing_class, file_path, import_map, local_type_map)

            if resolved:
                callee_id, confidence = resolved
                call_info.resolved = True
                props = f"line:{call_info.line}"
                results.append((caller_id, callee_id, props, confidence))

        return results

    def _extract_call_info(
        self, node: ast.Call, file_path: str,
    ) -> Optional[CallInfo]:
        """从 ast.Call 提取调用信息"""
        func = node.func

        if isinstance(func, ast.Name):
            # 简单调用: foo()
            return CallInfo(
                caller_id="", callee_name=func.id, line=node.lineno)

        elif isinstance(func, ast.Attribute):
            # 属性调用: obj.method() 或 module.func()
            scope = self._get_attr_chain(func)
            if scope:
                return CallInfo(
                    caller_id="",
                    callee_name=scope[-1] if len(scope) > 1 else func.attr,
                    callee_scope=scope[0],
                    line=node.lineno)
            # 退化到只有 attribute name
            return CallInfo(
                caller_id="", callee_name=func.attr, line=node.lineno)

        return None

    def _get_attr_chain(self, node: ast.Attribute) -> Optional[list[str]]:
        """获取属性链，如 a.b.c() → ['a', 'b', 'c']"""
        parts = []
        current: ast.expr = node
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if isinstance(current, ast.Name):
            parts.append(current.id)
        elif isinstance(current, ast.Call):
            # foo().method() — 无法静态解析
            return None
        else:
            return None
        return list(reversed(parts))

    def _resolve_call(
        self, info: CallInfo, file_symbols: dict,
        graph: KnowledgeGraph, enclosing_class: str,
        file_path: str,
        import_map: dict[str, str],
        local_type_map: dict[str, str],
    ) -> Optional[tuple[str, str]]:
        """尝试将调用解析为图中的符号节点

        解析顺序：
        1. self.xxx / cls.xxx → 同类方法 (high)
        2. obj.method() → 同文件赋值推导 (high)
        3. 简单函数名 → 先检查是否是 import 的 alias (medium)
        4. 简单函数名 → 同文件 function (high)
        5. ClassName.method → 同文件类方法 (high)
        6. import_alias.method() → 利用 import 信息解析 (medium)
        7. 全局跨文件搜索 → 同名函数 (low)
        """
        name = info.callee_name

        # 1. self.method() / cls.method() → 同文件同类的 method (high)
        if info.callee_scope in ("self", "cls"):
            if enclosing_class:
                method_id = f"method://{file_path}::{enclosing_class}.{name}"
                if graph.get_node(method_id):
                    return (method_id, "high")
            return None

        # 2. obj.method() → 赋值推导 (high)
        #    例如: obj = Foo(); obj.bar() → 查找 Foo.bar
        #    例如: obj = ImportedClass(); obj.bar() → 查找 other/file.py::ImportedClass.bar
        if info.callee_scope and info.callee_scope in local_type_map:
            resolved_type = local_type_map[info.callee_scope]
            if "::" in resolved_type:
                # 跨文件类型: target_file::ClassName
                target_file, class_name = resolved_type.split("::", 1)
                method_id = f"method://{target_file}::{class_name}.{name}"
                if graph.get_node(method_id):
                    return (method_id, "high")
            else:
                # 同文件类型
                method_id = f"method://{file_path}::{resolved_type}.{name}"
                if graph.get_node(method_id):
                    return (method_id, "high")

        # 3. 简单函数名 → 先检查是否是 import 的 alias (medium)
        #    例如: from app.kg.types import GraphNode; GraphNode() → 解析到 app/kg/types.py 中的 GraphNode
        if not info.callee_scope and name in import_map:
            target_file = import_map[name]
            # 在目标文件中查找类/函数/方法
            class_id = f"class://{target_file}::{name}"
            if graph.get_node(class_id):
                return (class_id, "medium")
            func_id = f"func://{target_file}::{name}"
            if graph.get_node(func_id):
                return (func_id, "medium")
            method_id = f"method://{target_file}::{name}"
            if graph.get_node(method_id):
                return (method_id, "medium")

        # 4. 简单函数名 → 同文件的 function (high)
        if not info.callee_scope:
            func_id = f"func://{file_path}::{name}"
            if graph.get_node(func_id):
                return (func_id, "high")

        # 5. ClassName.method → 同文件类方法 (high)
        if info.callee_scope:
            class_id = f"class://{file_path}::{info.callee_scope}"
            if graph.get_node(class_id):
                method_id = f"method://{file_path}::{info.callee_scope}.{name}"
                if graph.get_node(method_id):
                    return (method_id, "high")

        # 6. import_alias.method() → 利用 import 信息解析 (medium)
        if info.callee_scope and info.callee_scope in import_map:
            target_file = import_map[info.callee_scope]
            # 在目标文件中查找方法
            method_id = f"method://{target_file}::{name}"
            if graph.get_node(method_id):
                return (method_id, "medium")
            # 也可能目标文件中的类名等于 alias
            class_id = f"class://{target_file}::{info.callee_scope}"
            if graph.get_node(class_id):
                method_id = f"method://{target_file}::{info.callee_scope}.{name}"
                if graph.get_node(method_id):
                    return (method_id, "medium")
            # 也可能是自由函数
            func_id = f"func://{target_file}::{name}"
            if graph.get_node(func_id):
                return (func_id, "medium")

        # 7. 全局跨文件搜索 → 同名函数 (low)
        for node in graph.find_nodes_by_name(name, exact=True):
            if node.type in (NODE_FUNCTION, NODE_METHOD):
                return (node.id, "low")

        return None

    @staticmethod
    def _get_node_id(
        file_path: str, node: ast.FunctionDef | ast.AsyncFunctionDef,
        parent_map: dict[ast.AST, ast.AST],
    ) -> str:
        """获取函数/方法的节点 ID

        根据父节点映射判断是否在类内。
        """
        parent = parent_map.get(node)
        if isinstance(parent, ast.ClassDef):
            return f"method://{file_path}::{parent.name}.{node.name}"
        return f"func://{file_path}::{node.name}"

    @staticmethod
    def _get_enclosing_class(
        node: ast.AST, parent_map: dict[ast.AST, ast.AST],
    ) -> str:
        """获取所属的类名（通过父节点链向上查找）"""
        current = node
        while current in parent_map:
            parent = parent_map[current]
            if isinstance(parent, ast.ClassDef):
                return parent.name
            current = parent
        return ""

    @staticmethod
    def _get_file_symbols(file_path: str, graph: KnowledgeGraph) -> dict:
        """获取文件中所有符号的映射"""
        symbols = {}
        node_ids = graph.get_node_ids_by_file(file_path)
        for nid in node_ids:
            node = graph.get_node(nid)
            if node:
                symbols[node.name] = node
        return symbols

    @staticmethod
    def _build_local_type_map(
        tree: ast.AST,
        import_map: dict[str, str],
    ) -> dict[str, str]:
        """从赋值语句构建变量类型映射

        处理模式:
        - obj = Foo() → {"obj": "Foo"}
        - obj = ImportedClass() → {"obj": "other/file.py::ImportedClass"}
        - self.foo = Foo() → {"foo": "Foo"}（简化，忽略 self 前缀）
        - 忽略复杂表达式（如 obj = get_foo()）

        遍历整个 AST（含函数体内部），收集所有 `var = ClassName()` 形式的
        赋值。由于实现简单，不处理作用域遮蔽，但在实际代码库中收益足够。
        """
        type_map: dict[str, str] = {}

        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign) or len(node.targets) != 1:
                continue

            target = node.targets[0]
            if not isinstance(node.value, ast.Call):
                continue

            # 获取构造的类名: Foo() → "Foo", module.Foo() → "module.Foo"
            callee = node.value.func
            if isinstance(callee, ast.Name):
                class_name = callee.id
            elif isinstance(callee, ast.Attribute):
                # 简化处理: a.b.Foo() → "a.b.Foo"
                parts = []
                current = callee
                while isinstance(current, ast.Attribute):
                    parts.append(current.attr)
                    current = current.value
                if isinstance(current, ast.Name):
                    parts.append(current.id)
                class_name = ".".join(reversed(parts))
            else:
                continue

            # 只记录类名构造（首字母大写）
            # 过滤掉标准库函数（如 dict(), list(), set()）
            first_part = class_name.split(".")[-1]
            if not first_part or not first_part[0].isupper():
                continue
            if first_part in ("dict", "list", "set", "tuple", "frozenset"):
                continue

            # 如果是 import 的类，记录完整路径: target_file::ClassName
            # 这样跨文件调用 obj.method() 也能解析
            if class_name in import_map:
                resolved_type = f"{import_map[class_name]}::{class_name}"
            else:
                resolved_type = class_name

            # 记录变量名 → 类型
            if isinstance(target, ast.Name):
                type_map[target.id] = resolved_type
            elif isinstance(target, ast.Attribute):
                if isinstance(target.value, ast.Name) and target.value.id in ("self", "cls"):
                    type_map[target.attr] = resolved_type

        return type_map

    def _build_import_map(self, file_path: str, graph: KnowledgeGraph, source: str) -> dict[str, str]:
        """构建当前文件的 import 映射: 符号名 → target_file_path

        直接从源码 AST 提取 import 信息，建立精确的符号名到目标文件路径的映射。
        例如:
          from app.kg.types import GraphNode, GraphRelationship
          → {"GraphNode": "app/kg/types.py", "GraphRelationship": "app/kg/types.py"}

          import os
          → {"os": "os"}  (标准库，后续解析时会过滤)
        """
        from app.kg.types import REL_IMPORTS
        import ast

        import_map: dict[str, str] = {}

        # 第一步: 从图中的 IMPORTS 关系建立 module → target_file 映射
        module_to_file: dict[str, str] = {}
        source_id = f"file://{file_path}"
        for rel in graph.iter_relationships_by_type(REL_IMPORTS):
            if rel.source_id == source_id:
                target_file = rel.target_id.replace("file://", "")
                module = rel.properties.get("module", "")
                if module:
                    module_to_file[module] = target_file

        # 第二步: 从 AST 提取 import 的符号名，匹配到 module
        try:
            tree = ast.parse(source, filename=file_path)
        except SyntaxError:
            return import_map

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                module = node.module
                target_file = module_to_file.get(module)
                if target_file:
                    for alias in node.names:
                        # alias.name 是导入的符号名
                        name = alias.asname or alias.name
                        import_map[name] = target_file
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    # import app.kg.types → alias.name = "app.kg.types"
                    # 尝试解析为本地文件
                    target_file = module_to_file.get(alias.name)
                    if target_file:
                        name = alias.asname or alias.name.split(".")[-1]
                        import_map[name] = target_file

        return import_map


class JSCallAnalyzer:
    """JS/TS 调用分析器

    使用正则提取函数调用模式。
    """

    # 方法调用: obj.method(args)
    _METHOD_CALL = re.compile(
        r'(?:this|self)\.(\w+)\s*\(',
        re.MULTILINE,
    )
    # 函数调用: func(args)
    _FUNC_CALL = re.compile(
        r'(?<![.\w])'     # 前面不是点或单词字符
        r'([a-zA-Z_]\w*)' # 函数名
        r'\s*\('          # 调用括号
        r'(?![^)]*=>)'    # 不是箭头函数
        r'(?![^)]*\{)',   # 不是函数声明
        re.MULTILINE,
    )
    # 需要排除的关键字（不是函数调用）
    _KEYWORDS = {
        'if', 'for', 'while', 'switch', 'catch', 'function',
        'typeof', 'instanceof', 'return', 'throw', 'yield',
        'import', 'export', 'new', 'delete', 'void',
        'try', 'class', 'extends', 'implements',
    }

    def analyze_file(
        self, file_path: str, source: str, graph: KnowledgeGraph,
    ) -> list[tuple[str, str, str, str]]:
        calls: list[tuple[str, str, str, str]] = []
        lines = source.split('\n')

        # 获取文件中定义的符号
        file_nodes = []
        for nid in graph.get_node_ids_by_file(file_path):
            n = graph.get_node(nid)
            if n and n.type in (NODE_FUNCTION, NODE_METHOD):
                file_nodes.append(n)

        # 查找 this.method() 调用
        for match in self._METHOD_CALL.finditer(source):
            line = source[:match.start()].count('\n') + 1
            method_name = match.group(1)
            # 查找该文件中的同名方法
            for n in file_nodes:
                if n.name == method_name and n.type == NODE_METHOD:
                    # 找到调用者（包含这个调用语句的函数）
                    caller = self._find_enclosing_function(lines, line, file_nodes)
                    if caller:
                        calls.append((caller.id, n.id, f"line:{line}", "high"))

        # 查找简单函数调用
        for match in self._FUNC_CALL.finditer(source):
            name = match.group(1)
            if name in self._KEYWORDS:
                continue
            line = source[:match.start()].count('\n') + 1
            # 查找同名函数
            for n in file_nodes:
                if n.name == name and n.type == NODE_FUNCTION:
                    caller = self._find_enclosing_function(lines, line, file_nodes)
                    if caller:
                        calls.append((caller.id, n.id, f"line:{line}", "high"))

        return calls

    @staticmethod
    def _find_enclosing_function(
        lines: list[str], line_no: int, nodes: list[GraphNode],
    ) -> Optional[GraphNode]:
        """找到包含某行的函数节点"""
        for n in nodes:
            if n.start_line and n.end_line:
                if n.start_line <= line_no <= n.end_line:
                    return n
        return None


# ── 统一调度 ──────────────────────────────────────────────────────────────


class CallAnalyzer:
    """统一调用分析器"""

    def __init__(self):
        self._py = PythonCallAnalyzer()
        self._js = JSCallAnalyzer()

    def analyze_file(
        self, file_path: str, source: str, graph: KnowledgeGraph,
    ) -> list[tuple[str, str, str, str]]:
        ext = os.path.splitext(file_path)[1].lower()
        if ext in (".py", ".pyi", ".pyx"):
            return self._py.analyze_file(file_path, source, graph)
        elif ext in (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts"):
            return self._js.analyze_file(file_path, source, graph)
        return []
