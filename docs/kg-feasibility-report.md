# KG 引擎改进可行性验证报告

> 验证日期: 2026-05-21
> 验证范围: P0-1 (Tree-sitter)、P0-2 (调用解析)、P0-3 (类型传播) 核心技术假设
> 验证方式: 最小可行原型 + 基线测量

---

## 验证项汇总

| 验证项 | 假设 | 结果 | 关键数据 |
|--------|------|------|---------|
| **V1** | 当前调用解析率可作为改进基线 | ✅ 已测量 | 解析率 **36.3%** (4510/12418)，0% 有 confidence 标记 |
| **V2** | 同文件赋值推导可提升解析率 | ⚠️ 技术可行但收益有限 | 当前代码库潜在匹配 **14 个** (占 orphaned method 4.5%) |
| **V3** | Tree-sitter 可扩展 Java/Go | ⚠️ 可行但 Query API 需重写 | Parser ✅ 可用，Query API 与 `ts_parser.py` 不兼容 |
| **V4** | 6级DAG 是最佳调用解析设计 | ❌ 否 | 扁平化设计在可维护性、可测试性上均优于 6级DAG |

---

## V1: 调用解析率基线

### 测量方法

对 `backend/` 目录（~340 文件）运行完整 pipeline，分析 CALLS 边质量。

### 关键数据

```
总节点: 4611
总关系: 13784
CALLS 边: 4510

置信度分布:
  high:     0 (0.0%)     ← 全部没有 confidence 标记
  medium:   0 (0.0%)
  low:      0 (0.0%)
  unknown:  4510 (100.0%)

Pipeline Stats:
  calls_resolved: 12418   ← 提取的调用点
  解析率 = 4510 / 12418 ≈ 36.3%

imports_resolved: 4       ← 极低，import 解析链路有严重问题
```

### 发现

1. **所有 CALLS 边都没有 confidence 标记**，说明当前 call_processor 没有区分解析质量
2. **`imports_resolved: 4`** 说明跨文件 import 解析几乎失效，这是跨文件调用解析率低的根因
3. **310 个 method 节点没有 CALLS 入边**（占 621 个 method 的 50%），有大量解析空间

---

## V2: 同文件赋值推导

### 验证方法

在基线图谱上后验分析：遍历所有 `.py` 文件，找出 `obj = ClassName(); obj.method()` 模式，检查 `method://file::ClassName.method` 是否存在于图中。

### 关键数据

```
扫描 Python 文件: 170
'obj = Class(); obj.method()' 潜在匹配: 14
 orphaned method 节点: 310
```

### 结论

- **技术可行**：同文件赋值推导确实能解析一些调用
- **收益有限**：当前代码库（FastAPI backend）中 OO 模式不密集，仅 14 个潜在匹配
- **高度依赖代码库风格**：面向对象密集的项目（如 Django/Java）收益会更高

**建议**：不必作为独立 Phase 实现，而是在现有 `call_processor.py` 中**增量添加** `_build_local_type_map` 逻辑。

---

## V3: Tree-sitter 扩展验证

### 验证方法

1. 安装 `tree-sitter-java` 和 `tree-sitter-go`
2. 用 `Language()` + `Parser()` 初始化并解析简单代码
3. 检查 Query API 兼容性

### 关键发现

```
✅ tree-sitter-java 安装成功
✅ tree-sitter-go 安装成功
✅ Parser 可正常解析 Java/Go 代码
⚠️ Query API 与 ts_parser.py 中代码不兼容
```

### 重大发现：`ts_parser.py` 当前未被 pipeline 使用

- `grep -rn "TreeSitterParser" backend/app/kg/` **仅在 ts_parser.py 自身中找到引用**
- pipeline 中没有任何 phase 导入或实例化 `TreeSitterParser`
- `ts_parser.py` 中的 Query API (`queries["symbols"].captures(tree.root_node)`) 在 tree-sitter 0.25.2 中**不存在**

### 结论

- **可扩展性得到验证**：新增语言只需安装包 + 添加初始化代码
- **但存在技术债务**：现有 `ts_parser.py` 需要重写 Query 部分以适配 tree-sitter 0.25.2
- **优先级调整**：由于 ts_parser 当前未被使用，扩展新语言的优先级应低于修复现有调用解析

---

## V4: 6级DAG vs 扁平化设计

### 验证方法

实现两种设计的极简原型，对比代码复杂度、数据访问路径、可测试性。

### 对比结果

| 维度 | 6级DAG | 扁平化 |
|------|--------|--------|
| 数据类数量 | 6 个 | 1 个 |
| 数据访问路径 | `stage4.call.call.call.call.line` | `result.line` |
| 新增推导规则成本 | 修改多个 stage 数据结构 | 添加一个字段 |
| 调试难度 | 需追踪 6 层转换 | 单步即可定位 |
| 单元测试 | 需 mock 5 个中间对象 | 直接断言结果字段 |

### 结论

**扁平化设计全面优于 6级DAG**。6级DAG 的形式化结构没有带来实际工程收益，反而增加了维护成本。

**建议**：在现有 `call_processor.py` 中增量增强 `_resolve_call`，不引入 6 级嵌套数据结构。

---

## 对改进计划的建议调整

基于验证结果，建议对原修改后计划做以下调整：

### 1. P0-1 Tree-sitter：降低优先级

- `ts_parser.py` 当前未被使用，全面替换 symbol_extractor 的 ROI 低
- **建议**：保持 Python `ast` 解析器不变，仅在需要解析 JS/TS/Java/Go 时才启用 Tree-sitter
- **工作量**：从 4-6h 降为 **2h**（仅安装包 + 验证可用性）

### 2. P0-2 调用解析：改为扁平化增量增强

- 放弃 6级DAG 设计
- 在现有 `call_processor.py` 中增量添加：
  - confidence 标记（high/medium/low）
  - 同文件赋值推导（轻量实现）
  - import 符号重定向（修复 `imports_resolved: 4` 的问题）
- **工作量**：从 6-8h 降为 **4-6h**

### 3. P0-3 crossFile：跳过或大幅简化

- 验证证明同文件赋值推导收益有限（14 个匹配）
- 跨文件类型传播复杂度高（拓扑排序 + 全局传播）
- **建议**：跳过独立的 crossFile Phase，仅在 P0-2 中处理简单的 import 别名推导

### 4. 新增优先项：修复 import 解析

`imports_resolved: 4` 是当前最严重的瓶颈。修复后跨文件调用解析率会自然提升。

---

## 下一步行动

1. **即时行动**（1-2 小时）：修复 `import_processor.py`，将 `imports_resolved` 从 4 提升到合理水平
2. **短期行动**（1 天）：在 `call_processor.py` 中增加 confidence 标记和同文件赋值推导
3. **中期行动**（2-3 天）：评估是否需要引入 Tree-sitter 解析非 Python 语言

---

> 报告生成: 2026-05-21
> 验证脚本已清理
