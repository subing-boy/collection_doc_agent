"""
==============================================================================
模块名称: main.py
功能描述: 个人文档管家 Agent 命令行与交互式主入口
          完美契合用户的两类输入场景：
          1. 输入文件路径 (doc/ppt): 触发解析、智能分类与安全物理存储。
          2. 输入提问或生成指令: 基于库内已有资产进行严格带出处的精准回答，
             或直接逆向综合生成新 Doc 报表或现代 16:9 商业 PPT。
可移植性: 支持交互式 Shell 交互与单行 CLI 指令；使用 rich 美化输出，并具备标准 print 兜底。
==============================================================================
"""

import sys
import re
import argparse
from pathlib import Path
from typing import Optional, Union, Tuple

# 尝试导入 rich 库实现精美终端排版，若未安装则自动回退
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.markdown import Markdown
    console = Console()
    HAS_RICH = True
except ImportError:
    HAS_RICH = False
    console = None

from core.agent_core import AgentCore


def resolve_input_file_path(raw_path: str) -> Optional[Path]:
    """
    智能解析并归一化用户输入的文件路径：
    1. 支持 Windows 反斜杠与盘符自动转换 (如 D:\\xxx -> /mnt/d/xxx, C:\\xxx -> /mnt/c/xxx)；
    2. 支持 WSL 跨系统路径 (\\\\wsl.localhost\\Ubuntu-26.04\\home\\...)；
    3. 支持用户漏输扩展名时，自动在磁盘上探测并补全 .docx 或 .pptx；
    4. 若成功解析出有效的 Office 文档实体，则返回 Path 对象；否则返回 None。
    """
    p_str = raw_path.strip('\"\' ')
    if not p_str:
        return None

    SUPPORTED_EXTS = [".docx", ".pptx", ".xlsx", ".msg", ".md", ".txt"]

    # 如果包含明显的自然语言提问特征且不以支持格式结尾，则不视为路径
    if any(q in p_str for q in ["？", "?", "为什么", "怎么", "什么", "如何"]) and not any(p_str.lower().endswith(ext) for ext in SUPPORTED_EXTS):
        return None

    # 1. 处理 \\wsl.localhost\Ubuntu\... 形式的路径
    if p_str.startswith(("\\\\wsl.localhost\\", "//wsl.localhost/")):
        match = re.search(r'[/\\\\]home[/\\\\].*', p_str)
        if match:
            p_str = match.group(0).replace('\\', '/')

    # 2. 处理 Windows 盘符 D:\ -> /mnt/d/
    if re.match(r'^[A-Za-z]:', p_str):
        drive = p_str[0].lower()
        rest = p_str[2:].replace('\\', '/').lstrip('/')
        p_str = f'/mnt/{drive}/{rest}'
    else:
        p_str = p_str.replace('\\', '/')

    target = Path(p_str).resolve()
    if target.is_file() and target.suffix.lower() in SUPPORTED_EXTS:
        return target

    # 3. 如果用户漏输了扩展名，在磁盘上尝试自动探测补全支持的后缀
    for ext in [".docx", ".pptx", ".xlsx", ".msg", ".md", ".txt", ".DOCX", ".PPTX", ".XLSX", ".MSG", ".MD", ".TXT"]:
        candidate = Path(f"{p_str}{ext}").resolve()
        if candidate.is_file():
            return candidate

    return None


def extract_file_path_from_text(raw_text: str) -> Optional[Path]:
    """
    从自然语言混合输入（如 '存下来D:\\文档资料\\系统架构规范' 或 '帮我把 D:\\xx.docx 归档'）中
    使用高精度正则表达式剥离提取潜在文件路径，并在磁盘上进行真实实体校验。
    
    提取规则（耗时 < 1ms，纯本地无 LLM 消耗）：
    1. 首先尝试将整句直接当作路径解析；
    2. 若不是纯路径，正则扫描 Windows 盘符路径 (如 D:\\xxx 或 D:/xxx)；
    3. 正则扫描 Linux/WSL 绝对路径 (如 /mnt/d/xxx 或 /home/xxx)；
    4. 对剥离出的路径候选采用后置清洗与逐词回退，并在磁盘上实时校验；
    5. 若在磁盘上真实存在对应的文档实体文件，则返回 Path；否则返回 None（确保零误杀）。
    """
    clean_text = raw_text.strip('\"\' ')
    if not clean_text:
        return None

    # 1. 尝试整句直接解析
    direct_res = resolve_input_file_path(clean_text)
    if direct_res:
        return direct_res

    # 2. 从混合长句中正则提取候选路径片段
    candidates = []

    # 模式 A: 匹配 Windows 盘符路径 (如 D:\xxx 或 D:/xxx)
    win_pat = re.compile(r'[A-Za-z]:[\\/][^?？\"\'\r\n\t]+')
    candidates.extend(win_pat.findall(clean_text))

    # 模式 B: 匹配 WSL / Linux 绝对路径 (如 /mnt/d/... 或 /home/...)
    linux_pat = re.compile(r'/(?:mnt/[a-zA-Z]|home/[^/\s]+)/[^?？\"\'\r\n\t]+')
    candidates.extend(linux_pat.findall(clean_text))

    # 模式 C: 匹配显式带支持扩展名的文件名片段
    ext_pat = re.compile(r'[^?？\s\"\'\r\n\t]+\.(?:docx|pptx|xlsx|msg|md|txt|DOCX|PPTX|XLSX|MSG|MD|TXT)')
    candidates.extend(ext_pat.findall(clean_text))

    # 3. 对每个候选逐词回退清洗并校验是否存在于磁盘
    trailing_puncts = "。，,！!？? \t\r\n；;"
    for cand in candidates:
        cand_clean = cand.rstrip(trailing_puncts)
        if not cand_clean:
            continue
        # 逐词从右侧回退削减，以兼容路径后紧跟修饰词的情形（如: "...Definition(11.3) 谢谢！"）
        parts = cand_clean.split(' ')
        while parts:
            sub_cand = ' '.join(parts).rstrip(trailing_puncts)
            res = resolve_input_file_path(sub_cand)
            if res and res.is_file():
                return res
            parts.pop()

    return None


def print_banner():
    """打印系统欢迎横幅与模式指引"""
    banner_text = (
        "[bold cyan]🤖 个人文档管家 Agent (Personal Doc & PPT Agent)[/bold cyan]\n"
        "[dim]基于 DeepSeek 驱动架构  •  多格式切片归档  •  带严格出处 RAG 问答  •  逆向生成 Doc/PPT[/dim]\n"
        "[bold green]✔ 已支持格式:[/bold green] [dim].docx, .pptx, .xlsx, .msg, .md, .txt[/dim]"
    )
    if HAS_RICH:
        console.print(Panel(banner_text, border_style="blue", expand=False))
    else:
        print("=" * 70)
        print("🤖 个人文档管家 Agent (Personal Doc & PPT Agent)")
        print("✔ 已支持格式: .docx, .pptx, .xlsx, .msg, .md, .txt")
        print("=" * 70)


def show_documents_table(agent: AgentCore):
    """格式化展示当前知识库已归档的文件清单"""
    docs = agent.list_documents()
    if not docs:
        msg = "当前知识库尚无文档，您可以输入已支持的文件路径（如 .docx, .pptx, .xlsx, .msg, .md, .txt）进行添加归档！"
        if HAS_RICH:
            console.print(f"[yellow]{msg}[/yellow]")
        else:
            print(msg)
        return

    if HAS_RICH:
        table = Table(title="📚 个人知识库已归档文档清单", border_style="cyan")
        table.add_column("文档分类", style="magenta", justify="center")
        table.add_column("原始文件名", style="bold green")
        table.add_column("总页/节数", justify="right")
        table.add_column("智能提炼摘要", style="dim", max_width=50)
        table.add_column("归档时间", justify="center")

        for d in docs:
            table.add_row(
                d["category"],
                d["original_filename"],
                str(d["page_count"]),
                d["summary"] or "无",
                d["created_at"]
            )
        console.print(table)
    else:
        print("\n--- 📚 个人知识库已归档文档清单 ---")
        for d in docs:
            print(f"[{d['category']}] {d['original_filename']} ({d['page_count']}页) - {d['summary']}")
        print("---------------------------------\n")


# ==============================================================================
# 不支持格式库与友好转换指引字典
# ==============================================================================
UNSUPPORTED_FORMAT_TIPS = {
    ".doc": "旧版 Word (.doc) 属于专有二进制格式，请在 Office/WPS 中另存为现代 (.docx) 格式后重新存入。",
    ".xls": "旧版 Excel (.xls) 属于专有二进制格式，请另存为现代 (.xlsx) 格式后重新存入。",
    ".ppt": "旧版 PowerPoint (.ppt) 属于专有二进制格式，请另存为现代 (.pptx) 格式后重新存入。",
    ".pdf": "PDF (.pdf) 格式目前正在演进规划中，建议当前转换为 Word (.docx) 或 Markdown (.md) 后存入。",
    ".zip": "压缩包 (.zip) 无法直接维持切片出处，请在本地解压后将内部文档逐一存入。",
    ".rar": "压缩包 (.rar) 无法直接维持切片出处，请解压后存入内部文档。",
    ".7z": "压缩包 (.7z) 无法直接维持切片出处，请解压后存入内部文档。",
    ".png": "纯图片 (.png) 暂未挂载 OCR 识别引擎，建议提取文字后以 .md 或 .docx 格式存入。",
    ".jpg": "纯图片 (.jpg) 暂未挂载 OCR 识别引擎，建议提取文字后以 .md 或 .docx 格式存入。",
    ".jpeg": "纯图片 (.jpeg) 暂未挂载 OCR 识别引擎，建议提取文字后以 .md 或 .docx 格式存入。",
    ".mp3": "音频多媒体文件 (.mp3) 暂未接入语音转录模型，建议转录为会议纪要文本后存入。",
    ".mp4": "视频文件 (.mp4) 暂未接入多模态解析引擎，建议整理为方案文档后存入。"
}


def check_unsupported_format_tip(file_path: Union[str, Path]) -> Optional[str]:
    """
    检查文件后缀是否属于已知的不支持格式，并给出针对性的友好转换操作建议
    """
    suffix = Path(str(file_path).strip('\"\' ')).suffix.lower()
    return UNSUPPORTED_FORMAT_TIPS.get(suffix)


def handle_ingest(agent: AgentCore, file_path_input: Union[str, Path]):
    """处理文档上传与分类存储"""
    # 优先拦截已知的不支持格式并给出友好指引
    tip = check_unsupported_format_tip(file_path_input)
    if tip:
        suffix = Path(str(file_path_input).strip('\"\' ')).suffix.lower()
        notice = (
            f"❌ 格式暂不受支持: [bold red]{suffix}[/bold red]\n"
            f"💡 操作建议: {tip}\n"
            f"📌 当前原生支持格式: [.docx, .pptx, .xlsx, .msg, .md, .txt]"
        )
        if HAS_RICH:
            console.print(Panel(notice, title="[yellow]存储格式能力边界提示[/yellow]", border_style="yellow"))
        else:
            print(f"\n⚠️ 格式暂不受支持: {suffix}\n操作建议: {tip}\n当前支持格式: [.docx, .pptx, .xlsx, .msg, .md, .txt]\n")
        return

    if isinstance(file_path_input, Path):
        p = file_path_input
    else:
        resolved = resolve_input_file_path(file_path_input)
        p = resolved if resolved else Path(file_path_input.strip('"\'')).resolve()

    if not p.is_file():
        err = (
            f"❌ 文件不存在或无法访问: {file_path_input}\n"
            f"提示: 如果是 Windows 路径 (如 D:\\文档\\xxx.docx)，系统会自动转为 WSL 路径 (/mnt/d/...)，请确认文件名或扩展名是否准确。"
        )
        if HAS_RICH:
            console.print(f"[bold red]{err}[/bold red]")
        else:
            print(err)
        return

    if HAS_RICH:
        console.print(f"[cyan]⏳ 正在解析并智能归类文档: {p.name}...[/cyan]")
    else:
        print(f"⏳ 正在解析并智能归类文档: {p.name}...")

    try:
        report = agent.ingest_document(p)
        status = report.get("status", "success")

        if status == "skipped_duplicate":
            # 象限 1: 完全重复提交，秒级跳过
            msg = (
                f"[bold yellow]⚡ {report['message']}[/bold yellow]\n"
                f"• 文档名称: [bold]{report['filename']}[/bold]\n"
                f"• 所属分类: [magenta]{report['category']}[/magenta]\n"
                f"• 一句话摘要: {report['summary']}\n"
                f"• 提示: 内容无任何修改，已跳过解析与向量化，防止知识库冗余。"
            )
            if HAS_RICH:
                console.print(Panel(msg, title="防重拦截", border_style="yellow"))
            else:
                print(f"⚡ [防重跳过] {report['message']}")

        elif status == "updated_version":
            # 象限 2: 同名内容变动，版本就地迭代刷新
            msg = (
                f"[bold cyan]🔄 {report['message']}[/bold cyan]\n"
                f"• 文档名称: [bold]{report['filename']}[/bold]\n"
                f"• 所属分类: [magenta]{report['category']}[/magenta]\n"
                f"• 新切片数: {report['chunks_count']} 个 (旧版本切片已级联清理)\n"
                f"• 最新摘要: {report['summary']}\n"
                f"• 存储路径: [dim]{report['stored_path']}[/dim]"
            )
            if HAS_RICH:
                console.print(Panel(msg, title="版本就地迭代", border_style="cyan"))
            else:
                print(f"🔄 [版本刷新] {report['message']}")

        elif status == "aliased_duplicate":
            # 象限 3: 异名同Hash，改名副本别名绑定
            msg = (
                f"[bold magenta]📎 {report['message']}[/bold magenta]\n"
                f"• 当前提交: [bold]{report['filename']}[/bold]\n"
                f"• 关联原件: [bold green]{report['original_filename']}[/bold green]\n"
                f"• 所属分类: [magenta]{report['category']}[/magenta]\n"
                f"• 当前标签: {report['tags']}\n"
                f"• 提示: 已将新文件名登记为别名，物理上不生成重复切片。"
            )
            if HAS_RICH:
                console.print(Panel(msg, title="别名映射关联", border_style="magenta"))
            else:
                print(f"📎 [别名关联] {report['message']}")

        else:
            # 象限 4: 全新文件入库
            msg = (
                f"[bold green]✔ {report.get('message', '文档已成功分类归档！')}[/bold green]\n"
                f"• 文档名称: [bold]{report['filename']}[/bold]\n"
                f"• 归类结果: [magenta]{report['category']}[/magenta]\n"
                f"• 提炼标签: {report['tags']}\n"
                f"• 一句话摘要: {report['summary']}\n"
                f"• 知识切片数: {report['chunks_count']} 个\n"
                f"• 物理存储至: [dim]{report['stored_path']}[/dim]"
            )
            if HAS_RICH:
                console.print(Panel(msg, title="全新入库完成", border_style="green"))
            else:
                print(f"✔ 归档成功: [{report['category']}] -> {report['stored_path']}")
                print(f"  切片数: {report['chunks_count']}, 摘要: {report['summary']}")
    except Exception as e:
        err = f"❌ 归档失败: {e}"
        if HAS_RICH:
            console.print(f"[bold red]{err}[/bold red]")
        else:
            print(err)


def handle_ask(agent: AgentCore, query: str):
    """处理精准知识溯源问答"""
    if HAS_RICH:
        console.print(f"\n[cyan]🔍 正在检索知识库切片并生成带出处的答案...[/cyan]")
    else:
        print("\n🔍 正在检索知识库切片...")

    res = agent.ask(query)

    # 打印答案
    if HAS_RICH:
        console.print(Panel(Markdown(res["answer"]), title="💡 Agent 回答", border_style="green"))
        if res.get("sources"):
            console.print("[bold yellow]📌 知识出处证据列表:[/bold yellow]")
            for idx, s in enumerate(res["sources"], start=1):
                console.print(f"  {idx}. [bold]{s['source_filename']}[/bold] -> [cyan]{s['location_label']}[/cyan] (相关度: {s['score']})")
    else:
        print("\n💡 Agent 回答:\n" + res["answer"])
        if res.get("sources"):
            print("\n📌 知识出处证据列表:")
            for idx, s in enumerate(res["sources"], start=1):
                print(f"  {idx}. {s['source_filename']} -> {s['location_label']} (得分: {s['score']})")
    print()


def extract_generation_intent_and_target_dir(raw_text: str) -> Optional[Tuple[str, str, Optional[Path]]]:
    """向后兼容辅助函数：委托给 IntentRouter"""
    from core.intent_router import IntentRouter
    router = IntentRouter()
    res = router.analyze_intent(raw_text)
    if res.get("intent") in ("make_doc", "make_ppt"):
        action_type = "ppt" if res["intent"] == "make_ppt" else "doc"
        return action_type, res.get("topic", raw_text), res.get("target_dir")
    return None


def handle_make_doc(agent: AgentCore, topic: str, output_dir: Optional[Path] = None):
    """处理逆向生成 Word 总结报告"""
    if HAS_RICH:
        console.print(f"[cyan]📝 正在综合资料生成 Word 技术需求与方案文档: {topic}...[/cyan]")
    else:
        print(f"📝 正在生成 Word 技术需求与方案文档: {topic}...")

    out_path = agent.generate_new_doc(topic, output_dir=output_dir)
    msg = f"✔ Word 方案文档 (.docx) 已成功导出至:\n{out_path}"
    if HAS_RICH:
        console.print(Panel(msg, border_style="blue"))
    else:
        print(msg)


def handle_make_ppt(agent: AgentCore, topic: str, output_dir: Optional[Path] = None):
    """处理逆向生成 16:9 商业 PPT"""
    if HAS_RICH:
        console.print(f"[cyan]📊 正在综合资料规划并渲染 16:9 商业 PPT: {topic}...[/cyan]")
    else:
        print(f"📊 正在生成 PPT: {topic}...")

    out_path = agent.generate_new_ppt(topic, output_dir=output_dir)
    msg = f"✔ 演示文稿 (.pptx) 已成功导出至:\n{out_path}"
    if HAS_RICH:
        console.print(Panel(msg, border_style="blue"))
    else:
        print(msg)


def format_surrogate_error_notice(e: Exception) -> str:
    """
    针对 Unicode 代理字符（如 \\udce5）截断异常生成清晰友好的诊断说明
    说明空格或退格切断了 UTF-8 多字节导致识别成了 \\udce5
    """
    return (
        f"运行时出现异常: {e}\n\n"
        f"💡 编码原理解析: 说明空格切断了utf-8字节导致识别成了\\udce5 (中文多字节截断导致代理字符异常)。\n"
        f"建议: 请检查该位置的输入，删除残缺的断裂字符，重新完整输入中文字符。"
    )


def run_interactive_loop(agent: AgentCore):
    """
    运行交互式 Shell 会话
    智能自动识别用户意图：
    - 快车道 (Fast Lane): 退出指令、文件列表、磁盘实体文件路径直接命中；
    - 慢车道 (Slow Lane): 快慢双车道 IntentRouter 精准识别 make_doc / make_ppt / ask 并分流。
    """
    print_banner()
    help_info = (
        "💡 [bold]快速操作指南[/bold]:\n"
        "  1. [cyan]输入文档路径[/cyan]: 自动执行切片、分类并存储入库\n"
        "     • [bold green]✔ 支持格式[/bold green]: .docx, .pptx, .xlsx, .msg, .md, .txt\n"
        "     • [bold yellow]❌ 不支持格式[/bold yellow]: .doc/.xls/.ppt (建议另存为现代格式), .pdf (规划中), .zip, 图片/音视频\n"
        "  2. [cyan]输入问题[/cyan] (如 '方案的核心架构是什么'): 自动检索并带准确出处回答\n"
        "  3. [cyan]自然语言生成需求文档[/cyan] (如 '制作一个live mode vad需求方案 放在D:\\download'): 自动导出 Word\n"
        "  4. [cyan]自然语言生成演示文稿[/cyan] (如 '总结xxx制作ppt到D:\\download'): 自动导出 PPT\n"
        "  5. [cyan]list[/cyan]: 查看当前知识库已归档的文件列表\n"
        "  6. [cyan]exit / quit[/cyan]: 退出系统\n"
    )
    if HAS_RICH:
        console.print(Panel(help_info, border_style="dim"))
    else:
        print(help_info)

    while True:
        try:
            if HAS_RICH:
                user_input = console.input("[bold green]Agent > [/bold green]").strip()
            else:
                user_input = input("Agent > ").strip()

            if not user_input:
                continue

            # 1. 退出命令 (快车道)
            if user_input.lower() in ("exit", "quit", "q"):
                if HAS_RICH:
                    console.print("[dim]👋 再见！知识库已妥善保存。[/dim]")
                else:
                    print("再见！")
                break

            # 2. 查看文件清单 (快车道)
            elif user_input.lower() in ("list", "ls", "查看文件"):
                show_documents_table(agent)

            # 3. 显式上传归档指令 (快车道)
            elif user_input.startswith(("ingest ", "add ", "上传 ", "/add ", "归档 ", "存入 ", "保存 ")):
                raw_path = user_input.split(" ", 1)[1]
                handle_ingest(agent, raw_path)

            # 4. 智能实体探测与零 LLM 意图分流 (纯存文档 vs 边存边答) (快车道)
            elif (detected_file := extract_file_path_from_text(user_input)) is not None:
                stripped_query = user_input.replace(str(detected_file), "").strip()
                has_ask_intent = any(k in stripped_query for k in [
                    "？", "?", "总结", "讲了什么", "概括", "分析", "架构是什么", "介绍", "什么是", "核心内容", "如何", "怎样"
                ])
                handle_ingest(agent, detected_file)
                if has_ask_intent:
                    handle_ask(agent, user_input)

            # 5. 快慢双车道意图路由器 (涵盖 make_doc, make_ppt 与 ask)
            else:
                intent_res = agent.intent_router.analyze_intent(user_input)
                action = intent_res.get("intent", "ask")
                topic = intent_res.get("topic") or user_input
                target_dir = intent_res.get("target_dir")

                if action == "make_doc":
                    handle_make_doc(agent, topic, output_dir=target_dir)
                elif action == "make_ppt":
                    handle_make_ppt(agent, topic, output_dir=target_dir)
                else:
                    handle_ask(agent, user_input)

        except KeyboardInterrupt:
            print("\n会话已终止。")
            break
        except Exception as e:
            err_msg = str(e)
            if "surrogates not allowed" in err_msg or "\\udce5" in repr(e) or "\udce5" in err_msg:
                notice = format_surrogate_error_notice(e)
                if HAS_RICH:
                    console.print(Panel(notice, title="[red]UTF-8 字符编码截断[/red]", border_style="red"))
                else:
                    print(f"⚠️ {notice}")
            else:
                if HAS_RICH:
                    console.print(f"[bold red]运行时出现异常: {e}[/bold red]")
                else:
                    print(f"运行时出现异常: {e}")


def main():
    """主程序入口与参数解析"""
    parser = argparse.ArgumentParser(description="个人文档管家 Agent 命令行工具")
    subparsers = parser.add_subparsers(dest="command", help="子命令模式")

    # 子命令 1: 上传/分类
    parser_ingest = subparsers.add_parser("ingest", help="上传并分类存储一个 doc/ppt 文档")
    parser_ingest.add_argument("file_path", type=str, help="待归档的文件路径 (.pptx 或 .docx)")

    # 子命令 2: 溯源问答
    parser_ask = subparsers.add_parser("ask", help="对已有知识库进行带出处问答")
    parser_ask.add_argument("query", type=str, help="问题内容")

    # 子命令 3: 查看文档清单
    subparsers.add_parser("list", help="查看知识库已归档文档列表")

    # 子命令 4: 生成 Word 报告
    parser_doc = subparsers.add_parser("make-doc", help="综合资料生成 Word 总结报告")
    parser_doc.add_argument("topic", type=str, help="文档主题")

    # 子命令 5: 生成 PPT 演示文稿
    parser_ppt = subparsers.add_parser("make-ppt", help="综合资料生成 16:9 现代版式 PPT")
    parser_ppt.add_argument("topic", type=str, help="PPT 主题")

    args = parser.parse_args()
    agent = AgentCore()

    if args.command == "ingest":
        handle_ingest(agent, args.file_path)
    elif args.command == "ask":
        handle_ask(agent, args.query)
    elif args.command == "list":
        show_documents_table(agent)
    elif args.command == "make-doc":
        handle_make_doc(agent, args.topic)
    elif args.command == "make-ppt":
        handle_make_ppt(agent, args.topic)
    else:
        # 无参数传入时默认进入交互式 Shell
        run_interactive_loop(agent)


if __name__ == "__main__":
    main()
