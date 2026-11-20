# 目标

在系统中实现支持用户自定义编辑的 PPT 生成 Prompt 模板、自然语言长句“制作 PPT”意图识别与自定义保存目录输出：
1. 独立可配置的 PPT 提示词模板：在项目根目录设立 `prompts/ppt_prompt.txt`，支持 `{topic}` 与 `{context_materials}` 动态占位符，支持用户随时自由修改并在每次制作 PPT 前热加载读取；
2. 口语化长句“制作 PPT”意图识别：识别如 `总结一下...生成ppt到D:\download路径下` 或 `制作ppt` 等意图，准确提取核心主题，杜绝误入普通问答流；
3. 自定义导出目录支持：提取句中指定的目标目录（如 `D:\download` 自动映射为 `/mnt/d/download/`），若目录不存在则自动创建，并将生成的 `.pptx` 实体文件直接落盘至用户指定的自定义目录；
4. 真实执行与维测记录：真正调用 PPT 生成链路与底层 `PPTGenerator`，并在 `agent_debug.txt` 维测日志中完整记录本次工具调用的 Prompt 及生成的文件路径。

# 范围

## 目录结构

### 新建
- `prompts/ppt_prompt.txt`: 独立可配置的 PPT 提示词模板文件。

### 修改
- `config.py`: 新增 `PROMPTS_DIR` 与 `PPT_PROMPT_TEMPLATE_PATH` 配置项。
- `generators/ppt_generator.py`: `generate_presentation` 支持接收自定义 `output_dir`。
- `generators/doc_generator.py`: `generate_document` 同步支持接收自定义 `output_dir`。
- `core/agent_core.py`: `generate_new_ppt` 在每次生成前动态读取 `prompts/ppt_prompt.txt`，支持透传 `output_dir` 并记录维测轨迹。
- `main.py`: 实现自然语言长句中“制作 PPT/Word”意图与目标输出路径（如 `到D:\download`）的正则抽取、清洗与分流。
- `tests/test_skeleton.py`: 增加针对自定义 Prompt 读取、口语化生成意图与导出至沙箱自定义目录的自动化测试用例。

### 明确不建
- 不引入外部重型 PPT 渲染引擎，继续沿用纯 Python `python-pptx`。

# 非目标

- 不改变已有的普通知识库问答与四象限文档入库逻辑。

# 验收示例

- 用户输入 `总结一下live mode device + ca + ai 的主要内容包括流程 生成ppt到D:\download路径下`，系统能精准识别出“生成 PPT”意图，提取出主题 `live mode device + ca + ai 的主要内容包括流程`，并将目标保存目录解析为 `/mnt/d/download`。
- 动态读取 `prompts/ppt_prompt.txt` 作为大模型生成的指导规范，修改该文件后下一次生成即刻热生效。
- 生成的 `.pptx` 实体文件成功直接输出到用户指定的自定义目录（若未指定则默认输出至 `data/output/`）。
- 全套端到端自动化测试套件继续 100% 通过，沙箱自动销毁无残留。
