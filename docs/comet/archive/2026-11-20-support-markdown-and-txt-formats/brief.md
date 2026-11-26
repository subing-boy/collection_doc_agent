# 目标

在 Agent 知识资产摄取与管理管线中新增支持 Markdown（`.md`）与纯文本（`.txt`）两大核心技术文档格式：
1. Markdown 与文本解析器（`MarkdownParser`）：基于 Python 原生轻量文本处理（0 额外第三方依赖），自动识别 `#` 标题层级（H1/H2/H3/H4），构建带有章节面包屑路径的结构化语义切片，出处坐标精准记录至章节名称（如 `[出处: Device_Sensor_Design_ODM_V1.0.md, 1.2 硬件接口规范]`）；
2. 路径归一化与后缀补齐增强：在 `main.py` 的白名单与磁盘自动探测逻辑中追加 `.md` 与 `.txt`，支持用户输入类似 `D:\download\Device_Sensor_Design_ODM_V1.0`（漏输后缀）时秒级自动探测到真实存在的 `.md` 文件并触发分类入库；
3. 解析工厂与路由统一接入：在 `parsers/__init__.py` 注册 `MarkdownParser`，保持底层 SQLite、向量检索与四象限防重逻辑零侵入无缝复用。

# 范围

## 目录结构

### 新建
- `parsers/markdown_parser.py`: 基于 Python 内置文本处理实现 `MarkdownParser`，支持 `#` 标题层级切片与纯文本兜底分块。

### 修改
- `parsers/__init__.py`: 注册 `MarkdownParser` 到全局解析工厂分发链。
- `main.py`: 在路径探测与自动补齐算法中增加对 `.md` 与 `.txt` 扩展名支持。
- `tests/test_skeleton.py`: 新增针对 Markdown 格式的切片、入库、漏输后缀自动补齐与溯源问答自测用例。

### 明确不建
- 不引入外部重型 Markdown 渲染引擎，保持纯 Python 零依赖跨平台轻量设计。

# 非目标

- 不改变已有的 Word、PPT、Excel 与 MSG 解析功能。
- 不改变底层 RAG 评分与四象限去重规则。

# 验收示例

- 输入省略了 `.md` 后缀的路径 `D:\download\Device_Sensor_Design_ODM_V1.0`，系统能自动在磁盘探测到真实 `.md` 实体，成功触发文档分类与入库，绝不落入自然语言问答流。
- 输入包含多级标题的 `.md` 文件，解析器能按 `#` 标题层级提取切片并正确维护章节面包屑标签。
- 针对 `.md` 文档内容提问时，RAG 回答必须严格包含 `[出处: xx.md, 章节坐标]` 标记。
- 全套端到端自动化测试套件继续 100% 通过，沙箱自动销毁无残留。
