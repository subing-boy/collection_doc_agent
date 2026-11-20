# 目标

在 Agent 解析与存储管线中新增支持 Excel 表格（`.xlsx`）与 Outlook 邮件（`.msg`）两大高频办公格式：
1. Excel 解析器（`ExcelParser`）：基于纯 Python `openpyxl` 库，按 Sheet 遍历并采用“表头保持的自解释切片策略”，确保数据行与列名强绑定，出处坐标精准记录到工作表名称与行号区间；
2. 邮件解析器（`MSGParser`）：基于纯 Python `extract-msg` 库，抽取发件人、收件人、主题、时间与正文，将结构化邮件头置顶作为切片前置上下文，出处坐标精准记录至发件人与时间；
3. 解析工厂与路由升级：在 `parsers/__init__.py` 注册两大解析器，在 `main.py` 的智能路径提取器中支持 `.xlsx` 与 `.msg` 自动识别与补齐；
4. 保持底层 SQLite、向量检索与四象限防重逻辑零侵入无缝复用。

# 范围

## 目录结构

### 新建
- `parsers/excel_parser.py`: 基于 `openpyxl` 实现 `ExcelParser`，完成多 Sheet 遍历与带表头表格切片。
- `parsers/msg_parser.py`: 基于 `extract-msg` 实现 `MSGParser`，完成邮件头抽取与结构化通信切片。

### 修改
- `parsers/__init__.py`: 注册 `ExcelParser` 与 `MSGParser` 到全局解析器调度列表。
- `requirements.txt`: 补充 `openpyxl>=3.1.0` 与 `extract-msg>=0.48.0`。
- `main.py`: 在路径探测与自动补齐算法中增加对 `.xlsx` 与 `.msg` 扩展名支持。
- `tests/test_skeleton.py`: 增加针对 Excel 与 MSG 的生成、切片、分类与带出处问答自动化测试用例。

### 明确不建
- 不引入外部 C/C++ 重型编译依赖，保持纯 Python 跨平台轻量设计。
- 不强制要求本地安装 Microsoft Office 或 Outlook 客户端。

# 非目标

- 不改变已有的 Word 与 PPT 解析逻辑。
- 不改变底层四象限去重和 RAG 问答评分机制。

# 验收示例

- 输入 `.xlsx` 文件，能按 Sheet 成功提取保留表头的 Markdown 表格切片，精准标注工作表与行号，并成功分类归档与向量落库。
- 输入 `.msg` 邮件文件，能完整提取发件人、主题、时间与正文，生成带通信头的邮件切片并成功归档。
- 针对 Excel 数据或邮件决议提问时，回答中必须严格附带 `[出处: xx.xlsx, 工作表: xx, 行号]` 或 `[出处: xx.msg, 发件人: xx]`。
- 全套端到端自动化测试套件继续 100% 通过，沙箱自动销毁无残留。
