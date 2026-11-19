# 目标

在项目中构建系统级维测轨迹日志引擎（Harness Trace Logger）：
1. 在项目根目录下生成直观易读的单个文本日志 `agent_debug.txt`，结构化、透明化呈现每一次提问中 Harness 调度底座与 LLM 之间的多轮往返全过程；
2. 完整记录六大核心维测要素：System Prompt、历史对话上下文、可用工具列表、Harness 实际调用的工具与召回切片结果、当前轮次发给 LLM 的最终 Prompt、LLM 原始返回的自然语言回答；
3. 支持在 `.env` 中通过 `AGENT_DEBUG=true|false` 一键控制总开关，关闭时保持 0 额外耗时与 0 磁盘 I/O；
4. 实现安全的定时定量自动轮转清理机制：单个日志文件上限设定为 **10MB**（`AGENT_DEBUG_MAX_MB=10`），满 10MB 自动滚动，最多保留 2 份历史备份（`agent_debug.txt.1`, `agent_debug.txt.2`），超额自动淘汰最老日志，彻底杜绝日志无限膨胀；
5. 在 `.gitignore` 中配置日志忽略规则，防止本地调试轨迹误提交至 GitHub。

# 范围

## 目录结构

### 新建
- `core/trace_logger.py`: 实现基于 Python 原生 `RotatingFileHandler` 的维测日志引擎与结构化 `TraceContext` 轨迹收集器。

### 修改
- `config.py`: 新增维测开关、日志文件名、单文件 10MB 上限与备份数配置项。
- `.env.example`: 补充维测相关环境变量注释模板。
- `core/agent_core.py`: 在 `ask()` 核心生命周期中装配轨迹追踪打点。
- `.gitignore`: 增加 `agent_debug.txt*` 规则。
- `tests/test_skeleton.py`: 新增维测开关生效性与 10MB 滚动清理机制的自动化测试用例。

### 明确不建
- 不引入外部重型 APM 或复杂分布式追踪框架，保持纯 Python 零依赖轻量化设计。

# 非目标

- 维测关闭时绝不增加任何额外的运行开销或网络调用。
- 不修改现有的业务 Prompt 和 RAG 回答内容。

# 验收示例

- 当开启 `AGENT_DEBUG=true` 时，执行提问后根目录下自动生成 `agent_debug.txt`，内容清晰排版且完整包含六大维测信息（System Prompt、历史对话、可用工具、调用工具与检索得分、发送给 LLM 的 Prompt、AI 原始回复）。
- 当配置 `AGENT_DEBUG=false` 时，执行提问绝不输出或写入任何调试日志，保持纯净。
- 自动滚动机制生效：当日志文件达到 10MB 时自动滚动为 `.1`，历史备份最多保留 2 份，更早的旧日志自动删除。
- 全套端到端自动化测试套件继续 100% 通过，沙箱自动清理无残留。
