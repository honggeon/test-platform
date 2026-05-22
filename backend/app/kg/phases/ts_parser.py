"""
⚠️  废弃警告 / DEPRECATED

本文件当前不可用，原因如下：
1. tree-sitter 0.25.2 的 Query API 与代码中使用的接口不兼容
   - 0.25.2 中 Query 对象无 .captures() / .matches() 方法，需改用 QueryCursor
2. TreeSitterParser 类从未被 pipeline 任何模块导入使用

保留目的：其中的 query 模式（Python/JS/TS/TSX/Java/Go）可作为未来重写时的
设计参考。若需启用 Tree-sitter 支持，需：
- 改用 tree-sitter 0.25.2 的 QueryCursor API 重写所有 query 执行逻辑
- 补充安装 tree-sitter-java、tree-sitter-go 等语言包
- 在 pipeline 中注册为 symbol_extractor 的 fallback 或主解析器

当前生产解析器：backend/app/kg/phases/symbol_extractor.py (Python ast + 正则)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

from tree_sitter import Language, Parser, Query, Node


# ── 捕获的 AST 节点类型 ───────────────────────


@dataclass
class ExtractedSymbol:
    name: str
    kind: str              # class/function/method/variable/interface/enum
    start_line: int
    end_line: int
    parent_name: Optional[str] = None   # 封闭类名（method 的父类）
    doc_string: str = ""
    decorators: list[str] = field(default_factory=list)


@dataclass
class ExtractedImport:
    module_path: str              # 如 "app.kg.types"
    imported_names: list[tuple[str, Optional[str]]]  # [(name, alias), ...]
    is_from_import: bool          # from X import Y vs import X


@dataclass
class ExtractedCall:
    callee_name: str
    receiver: Optional[str]       # self / cls / obj / class_name
    arg_count: int
    line: int


@dataclass
class ExtractedHeritage:
    class_name: str
    parent_name: str
    rel_type: str                 # EXTENDS / IMPLEMENTS


@dataclass
class ParsedFile:
    file_path: str
    symbols: list[ExtractedSymbol] = field(default_factory=list)
    imports: list[ExtractedImport] = field(default_factory=list)
    calls: list[ExtractedCall] = field(default_factory=list)
    heritage: list[ExtractedHeritage] = field(default_factory=list)
    _source: str = ""  # 源码缓存，用于 extract helper


# ── Tree-sitter 统一解析器 ─────────────────────


class TreeSitterParser:
    """Tree-sitter 统一解析器

    按文件扩展名路由到对应语言的 Grammar。
    每个语言定义自己的 query 模式。
    """

    def __init__(self):
        self._parsers: dict[str, Parser] = {}
        self._queries: dict[str, dict[str, Query]] = {}

        # Python
        try:
            import tree_sitter_python as tspython
            py_lang = Language(tspython.language())
            py_parser = Parser(py_lang)
            self._parsers[".py"] = py_parser
            self._parsers[".pyi"] = py_parser
            self._queries[".py"] = self._build_python_queries(py_lang)
        except ImportError:
            pass

        # JavaScript
        try:
            import tree_sitter_javascript as tsjavascript
            js_lang = Language(tsjavascript.language())
            js_parser = Parser(js_lang)
            self._parsers[".js"] = js_parser
            self._parsers[".jsx"] = js_parser
            self._parsers[".mjs"] = js_parser
            self._parsers[".cjs"] = js_parser
            self._queries[".js"] = self._build_js_queries(js_lang)
            self._queries[".jsx"] = self._build_jsx_queries(js_lang)
        except ImportError:
            pass

        # TypeScript
        try:
            import tree_sitter_typescript as tstypescript
            ts_lang = Language(tstypescript.language_typescript())
            ts_parser = Parser(ts_lang)
            self._parsers[".ts"] = ts_parser
            self._parsers[".mts"] = ts_parser
            self._parsers[".cts"] = ts_parser
            self._queries[".ts"] = self._build_ts_queries(ts_lang)

            tsx_lang = Language(tstypescript.language_tsx())
            tsx_parser = Parser(tsx_lang)
            self._parsers[".tsx"] = tsx_parser
            self._queries[".tsx"] = self._build_tsx_queries(tsx_lang)
        except ImportError:
            pass

    def is_supported(self, ext: str) -> bool:
        return ext.lower() in self._parsers

    def parse_file(self, file_path: str, source: str) -> Optional[ParsedFile]:
        """解析单个文件，返回所有提取信息"""
        ext = os.path.splitext(file_path)[1].lower()
        parser = self._parsers.get(ext)
        if not parser:
            return None

        tree = parser.parse(bytes(source, "utf-8"))
        queries = self._queries.get(ext, {})

        result = ParsedFile(file_path=file_path, _source=source)

        # 按顺序执行各种 query
        if "symbols" in queries:
            result.symbols = self._query_symbols(queries["symbols"], tree.root_node, source)

        if "imports" in queries:
            result.imports = self._query_imports(queries["imports"], tree.root_node, source)

        if "calls" in queries:
            result.calls = self._query_calls(queries["calls"], tree.root_node, source)

        if "heritage" in queries:
            result.heritage = self._query_heritage(queries["heritage"], tree.root_node, source)

        return result

    # ── Symbol query ────────────────────────────

    def _query_symbols(
        self, query: Query, root: Node, source: str,
    ) -> list[ExtractedSymbol]:
        """执行符号提取 query"""
        symbols: list[ExtractedSymbol] = []
        seen_names: set[tuple[str, int]] = set()

        for match_idx, (pattern_idx, captures) in enumerate(query.captures(root)):
            cap_dict: dict[str, list[Node]] = {}
            for cap_name, nodes in captures.items():
                cap_dict.setdefault(cap_name, []).extend(nodes)

            # 尝试不同类型的定义
            for kind, name_key, defn_key in [
                ("class", "class_name", "class_def"),
                ("function", "func_name", "func_def"),
                ("method", "method_name", "method_def"),
                ("interface", "iface_name", "iface_def"),
                ("enum", "enum_name", "enum_def"),
                ("variable", "var_name", "var_def"),
            ]:
                name_nodes = cap_dict.get(name_key, [])
                if not name_nodes:
                    continue
                defn_nodes = cap_dict.get(defn_key, [])
                decorator_nodes = cap_dict.get("decorator", [])
                body_nodes = cap_dict.get("body", [])

                for i, name_node in enumerate(name_nodes):
                    sym_name = self._node_text(name_node, source)

                    # 去重
                    key = (sym_name, name_node.start_point[0] + 1)
                    if key in seen_names:
                        continue
                    seen_names.add(key)

                    # 找到定义节点
                    defn_node: Optional[Node] = None
                    if i < len(defn_nodes):
                        defn_node = defn_nodes[i]

                    if not defn_node:
                        start_line = name_node.start_point[0] + 1
                        end_line = name_node.end_point[0] + 1
                    else:
                        start_line = defn_node.start_point[0] + 1
                        end_line = self._node_end_line(defn_node)

                    # docstring
                    doc = ""
                    if defn_node and kind in ("class", "function"):
                        doc = self._extract_docstring(defn_node, source)

                    # decorators
                    decorators = []
                    for d in decorator_nodes:
                        d_text = self._node_text(d, source).lstrip("@")
                        decorators.append(d_text)

                    # parent_name for methods
                    parent_name = None
                    if kind == "method" and defn_node:
                        parent = defn_node.parent
                        if parent and parent.type == "class_definition":
                            cn = parent.child_by_field_name("name")
                            if cn:
                                parent_name = self._node_text(cn, source)

                    symbols.append(ExtractedSymbol(
                        name=sym_name,
                        kind=kind,
                        start_line=start_line,
                        end_line=end_line,
                        parent_name=parent_name,
                        doc_string=doc[:200],
                        decorators=decorators,
                    ))

                # 只处理第一个匹配到的类型
                if name_nodes:
                    break

        # 也处理 decorated_definition
        for _, captures in query.captures(root):
            cap_dict = {}
            for cap_name, nodes in captures.items():
                cap_dict.setdefault(cap_name, []).extend(nodes)

            if "decorator" in cap_dict and "defn" in cap_dict:
                # 已经包含在 symbols 查询中（装饰器在 class_def / func_def 上匹配）
                pass

        return symbols

    # ── Import query ────────────────────────────

    def _query_imports(
        self, query: Query, root: Node, source: str,
    ) -> list[ExtractedImport]:
        imports: list[ExtractedImport] = []

        for _, captures in query.captures(root):
            cap_dict: dict[str, list[Node]] = {}
            for cap_name, nodes in captures.items():
                cap_dict.setdefault(cap_name, []).extend(nodes)

            modules = cap_dict.get("module", [])
            names = cap_dict.get("imported_name", [])
            aliases = cap_dict.get("alias_name", [])
            is_from = "from_import" in cap_dict

            if not modules:
                continue

            for mod_node in modules:
                module_path = self._node_text(mod_node, source)
                imported = []
                for j, n in enumerate(names):
                    name_text = self._node_text(n, source)
                    alias_text = None
                    if j < len(aliases):
                        alias_text = self._node_text(aliases[j], source)
                    imported.append((name_text, alias_text or name_text))

                imports.append(ExtractedImport(
                    module_path=module_path,
                    imported_names=imported,
                    is_from_import=is_from,
                ))

        return imports

    # ── Call query ──────────────────────────────

    def _query_calls(
        self, query: Query, root: Node, source: str,
    ) -> list[ExtractedCall]:
        calls: list[ExtractedCall] = []

        for _, captures in query.captures(root):
            cap_dict: dict[str, list[Node]] = {}
            for cap_name, nodes in captures.items():
                cap_dict.setdefault(cap_name, []).extend(nodes)

            receivers = cap_dict.get("receiver", [])
            this_receivers = cap_dict.get("this_receiver", [])
            method_names = cap_dict.get("method_name", [])
            func_names = cap_dict.get("func_name", [])

            if method_names and (receivers or this_receivers):
                # method call: obj.method()
                receiver_text = None
                if receivers:
                    receiver_text = self._node_text(receivers[0], source)
                elif this_receivers:
                    receiver_text = "self"

                for mn in method_names:
                    calls.append(ExtractedCall(
                        callee_name=self._node_text(mn, source),
                        receiver=receiver_text,
                        arg_count=0,
                        line=mn.start_point[0] + 1,
                    ))

            elif func_names:
                # simple call: foo()
                for fn in func_names:
                    calls.append(ExtractedCall(
                        callee_name=self._node_text(fn, source),
                        receiver=None,
                        arg_count=0,
                        line=fn.start_point[0] + 1,
                    ))

        return calls

    # ── Heritage query ──────────────────────────

    def _query_heritage(
        self, query: Query, root: Node, source: str,
    ) -> list[ExtractedHeritage]:
        heritage: list[ExtractedHeritage] = []

        for _, captures in query.captures(root):
            cap_dict: dict[str, list[Node]] = {}
            for cap_name, nodes in captures.items():
                cap_dict.setdefault(cap_name, []).extend(nodes)

            class_names = cap_dict.get("class_name", [])
            parent_classes = cap_dict.get("parent_class", [])
            implements_nodes = cap_dict.get("implements_clause", [])

            for i, cn in enumerate(class_names):
                class_name = self._node_text(cn, source)
                if i < len(parent_classes):
                    parent_name = self._node_text(parent_classes[i], source)
                    heritage.append(ExtractedHeritage(
                        class_name=class_name,
                        parent_name=parent_name,
                        rel_type="EXTENDS",
                    ))
                for imp in implements_nodes:
                    heritage.append(ExtractedHeritage(
                        class_name=class_name,
                        parent_name=self._node_text(imp, source),
                        rel_type="IMPLEMENTS",
                    ))

        return heritage

    # ── Query builders ──────────────────────────

    def _build_python_queries(self, lang) -> dict[str, Query]:
        return {
            "symbols": Query(lang, """
                (class_definition
                  name: (identifier) @class_name
                  body: (block) @body) @class_def

                (function_definition
                  name: (identifier) @func_name
                  parameters: (parameters) @params) @func_def

                (assignment
                  left: (identifier) @var_name
                  right: (_) @var_value) @assignment

                (decorated_definition
                  decorator: (decorator) @decorator) @decorated_def

                (decorated_definition
                  definition: (function_definition name: (identifier) @func_name)) @decorated_func
            """),
            "imports": Query(lang, """
                (import_statement
                  name: (dotted_name) @module) @import_stmt

                (import_from_statement
                  module_name: (dotted_name) @module
                  (aliased_import
                    name: (dotted_name) @imported_name
                    alias: (identifier) @alias_name)?) @from_import

                (import_from_statement
                  module_name: (dotted_name) @module
                  (dotted_name) @imported_name) @from_import_simple
            """),
            "calls": Query(lang, """
                (call
                  function: (identifier) @func_name) @simple_call

                (call
                  function: (attribute
                    object: (identifier) @receiver
                    attribute: (identifier) @method_name)) @method_call

                (call
                  function: (attribute
                    object: (attribute
                      object: (identifier) @receiver))) @nested_call
            """),
            "heritage": Query(lang, """
                (class_definition
                  name: (identifier) @class_name
                  superclasses: (argument_list
                    (_) @parent_class)) @class_with_parent
            """),
        }

    def _build_js_queries(self, lang) -> dict[str, Query]:
        return {
            "symbols": Query(lang, """
                (class_declaration
                  name: (identifier) @class_name) @class_def

                (function_declaration
                  name: (identifier) @func_name) @func_def

                (method_definition
                  name: (property_identifier) @method_name) @method_def

                (variable_declaration
                  (variable_declarator
                    name: (identifier) @var_name)) @var_def
            """),
            "imports": Query(lang, """
                (import_statement
                  source: (string) @module
                  (import_clause
                    (identifier) @imported_name)?) @import_stmt

                (import_statement
                  source: (string) @module
                  (import_clause
                    (named_imports
                      (import_specifier
                        name: (identifier) @imported_name
                        alias: (identifier) @alias_name?))) @named_import
            """),
            "calls": Query(lang, """
                (call_expression
                  function: (identifier) @func_name) @simple_call

                (call_expression
                  function: (member_expression
                    object: (identifier) @receiver
                    property: (property_identifier) @method_name)) @method_call

                (call_expression
                  function: (member_expression
                    object: (this) @this_receiver
                    property: (property_identifier) @method_name)) @this_call
            """),
            "heritage": Query(lang, """
                (class_declaration
                  name: (identifier) @class_name
                  heritage: (class_heritage
                    (identifier) @parent_class)) @class_extends

                (class_declaration
                  name: (identifier) @class_name
                  heritage: (class_heritage
                    (_) @implements_clause)) @class_implements
            """),
        }

    def _build_jsx_queries(self, lang) -> dict[str, Query]:
        return self._build_js_queries(lang)

    def _build_ts_queries(self, lang) -> dict[str, Query]:
        return {
            "symbols": Query(lang, """
                (class_declaration
                  name: (type_identifier) @class_name) @class_def

                (function_declaration
                  name: (identifier) @func_name) @func_def

                (method_definition
                  name: (property_identifier) @method_name) @method_def

                (interface_declaration
                  name: (type_identifier) @iface_name) @iface_def

                (enum_declaration
                  name: (identifier) @enum_name) @enum_def

                (variable_declaration
                  (variable_declarator
                    name: (identifier) @var_name)) @var_def
            """),
            "imports": Query(lang, """
                (import_statement
                  source: (string) @module
                  (import_clause
                    (identifier) @imported_name)?) @import_stmt

                (import_statement
                  source: (string) @module
                  (import_clause
                    (named_imports
                      (import_specifier
                        name: (identifier) @imported_name
                        alias: (identifier) @alias_name?))) @named_import
            """),
            "calls": Query(lang, """
                (call_expression
                  function: (identifier) @func_name) @simple_call

                (call_expression
                  function: (member_expression
                    object: (identifier) @receiver
                    property: (property_identifier) @method_name)) @method_call

                (call_expression
                  function: (member_expression
                    object: (this) @this_receiver
                    property: (property_identifier) @method_name)) @this_call
            """),
            "heritage": Query(lang, """
                (class_declaration
                  name: (type_identifier) @class_name
                  heritage: (class_heritage
                    (type_identifier) @parent_class)) @class_extends

                (class_declaration
                  name: (type_identifier) @class_name
                  heritage: (class_heritage
                    (_) @implements_clause)) @class_implements
            """),
        }

    def _build_tsx_queries(self, lang) -> dict[str, Query]:
        return self._build_ts_queries(lang)

    # ── Utilities ───────────────────────────────

    @staticmethod
    def _node_text(node: Node, source: str) -> str:
        try:
            return source[node.start_byte:node.end_byte]
        except (IndexError, ValueError):
            return ""

    @staticmethod
    def _node_end_line(node: Node) -> int:
        try:
            return node.end_point[0] + 1
        except (AttributeError, TypeError):
            return 1

    @staticmethod
    def _extract_docstring(defn_node: Node, source: str) -> str:
        """从定义节点提取 docstring"""
        body = defn_node.child_by_field_name("body")
        if not body:
            return ""
        if body.named_child_count == 0:
            return ""
        first = body.named_child(0)
        if not first:
            return ""

        # Python: expression_statement > string
        if first.type == "expression_statement":
            child = first.named_child(0)
            if child and child.type == "string":
                return source[child.start_byte:child.end_byte]

        # JS/TS: expression_statement > string (template_string)
        if first.type == "expression_statement":
            child = first.named_child(0)
            if child and child.type in ("string", "template_string"):
                return source[child.start_byte:child.end_byte]

        return ""
