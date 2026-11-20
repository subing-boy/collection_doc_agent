# 目标

在 Agent 交互层构建“快慢双车道（Fast-Slow Dual Lane）”智能意图路由器（`IntentRouter`），彻底解决传统单一硬编码正则表达式枚举无法覆盖自然语言海量变体（如“制作需求方案 放在D:\download路径下”、“整一份说明书扔到D盘”）的根本缺陷：
1. 车道 1（本地快车道 - 0ms）：
   - 纯控制指令（`exit`, `list`）、显式命令行前缀（`make-doc ...`, `make-ppt ...`）以及磁盘实体文件直接命中入库，保持 0 延迟、0 Token 开销；
2. 车道 2（大模型语义慢车道 - 结构化意图分析）：
   - 遇到任何非显式命令的自然语言长句时，唤醒轻量级大模型语义路由器（`IntentRouter`）；
   - 输出标准结构化 JSON：`intent`（`make_doc` | `make_ppt` | `ask`）、`topic`（核心业务主题）、`target_dir`（目标导出路径）；
   - 自动完成 Windows 盘符路径归一化（如 `D:\download` ➔ `/mnt/d/download`）；
   - 具备断网/离线平滑降级能力（规则兜底，永不崩溃）；
3. 闭环工具派发与输出：
   - 若意图为 `make_doc`：自动调度 `handle_make_doc`，从知识库检索并直接导出排版好的 `.docx` 文件至用户指定的自定义目录；
   - 若意图为 `make_ppt`：自动调度 `handle_make_ppt`；
   - 若意图为 `ask`：自动调度 `handle_ask`。

# 范围

## 目录结构

### 新建
- `core/intent_router.py`: 实现 `IntentRouter` 类，负责快慢双车道意图分类与目标路径/主题抽取。
- `prompts/doc_prompt.txt`: 独立可配置的 Word 需求文档提示词模板文件，供用户自由定制文档结构。

### 修改
- `config.py`: 新增 `DOC_PROMPT_TEMPLATE_PATH` 配置项。
- `core/agent_core.py`: 集成 `IntentRouter`，`generate_new_doc` 动态读取 `doc_prompt.txt`。
- `main.py`: 在交互主循环中全面接入“快慢双车道”调度引擎。
- `tests/test_skeleton.py`: 新增针对口语化文档方案生成与语义慢车道分流的自动化测试用例。

### 明确不建
- 严禁在快车道发起不必要的外部网络调用，保持常用明确操作的毫秒级速度。

# 非目标

- 不改变已有的底层四象限防重、向量检索与 4 轮 Agent Loop 逻辑。

# 验收示例

- 输入 `“制作一个live mode vad的具体需求方案 放在D:\download路径下”`，系统不再误入问答流，而是精准识别为 `make_doc` 意图，提取主题 `live mode vad的具体需求方案` 与目标目录 `/mnt/d/download`，成功导出 `.docx` 文件。
- 输入各类口语化变体（如 `整一份 live mode 技术说明书 存到 D:\download` 或 `做个汇报ppt`），语义慢车道均能 100% 准确分流。
- 常用文件拖拽入库、`exit`、`list` 继续走快车道，保持 0 毫秒极速响应。
- 全套端到端自动化测试套件继续 100% 通过，沙箱自动销毁无残留。
