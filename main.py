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
import argparse
from pathlib import Path
from typing import Optional

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


def print_banner():
    """打印系统欢迎横幅与模式指引"""
    banner_text = (
        "[bold cyan]🤖 个人文档管家 Agent (Personal Doc & PPT Agent)[/bold cyan]\n"
        "[dim]基于 DeepSeek 驱动架构  •  多格式切片归档  •  带严格出处 RAG 问答  •  逆向生成 Doc/PPT[/dim]"
    )
    if HAS_RICH:
        console.print(Panel(banner_text, border_style="blue", expand=False))
    else:
        print("=" * 70)
        print("🤖 个人文档管家 Agent (Personal Doc & PPT Agent)")
        print("=" * 70)


def show_documents_table(agent: AgentCore):
    """格式化展示当前知识库已归档的文件清单"""
    docs = agent.list_documents()
    if not docs:
        msg = "当前知识库尚无文档，您可以输入一个 .docx 或 .pptx 文件路径进行添加归档！"
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


def handle_ingest(agent: AgentCore, file_path_str: str):
    """处理文档上传与分类存储"""
    p = Path(file_path_str.strip('"\'')).resolve()
    if not p.is_file():
        err = f"❌ 文件不存在: {p}"
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
        if HAS_RICH:
            msg = (
                f"[bold green]✔ 文档已成功分类归档！[/bold green]\n"
                f"• 文档名称: [bold]{report['filename']}[/bold]\n"
                f"• 归类结果: [magenta]{report['category']}[/magenta]\n"
                f"• 提炼标签: {report['tags']}\n"
                f"• 一句话摘要: {report['summary']}\n"
                f"• 知识切片数: {report['chunks_count']} 个\n"
                f"• 物理存储至: [dim]{report['stored_path']}[/dim]"
            )
            console.print(Panel(msg, title="入库完成", border_style="green"))
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


def handle_make_doc(agent: AgentCore, topic: str):
    """处理逆向生成 Word 总结报告"""
    if HAS_RICH:
        console.print(f"[cyan]📝 正在综合资料生成 Word 总结报告: {topic}...[/cyan]")
    else:
        print(f"📝 正在生成 Word 总结报告: {topic}...")

    out_path = agent.generate_new_doc(topic)
    msg = f"✔ Word 报告已成功导出至:\n{out_path}"
    if HAS_RICH:
        console.print(Panel(msg, border_style="blue"))
    else:
        print(msg)


def handle_make_ppt(agent: AgentCore, topic: str):
    """处理逆向生成 16:9 商业 PPT"""
    if HAS_RICH:
        console.print(f"[cyan]📊 正在综合资料规划并渲染 16:9 商业 PPT: {topic}...[/cyan]")
    else:
        print(f"📊 正在生成 PPT: {topic}...")

    out_path = agent.generate_new_ppt(topic)
    msg = f"✔ 演示文稿 (.pptx) 已成功导出至:\n{out_path}"
    if HAS_RICH:
        console.print(Panel(msg, border_style="blue"))
    else:
        print(msg)


def run_interactive_loop(agent: AgentCore):
    """
    运行交互式 Shell 会话
    智能自动识别用户意图：
    - 输入文件路径（.pptx/.docx）自动识别为分类入库；
    - 输入 make-doc / make-ppt 自动识别为生成；
    - 其余自然语言输入均作为溯源问答。
    """
    print_banner()
    help_info = (
        "💡 [bold]快速操作指南[/bold]:\n"
        "  1. [cyan]输入文档路径[/cyan] (如 test.pptx 或 document.docx): 自动执行切片、分类并存储\n"
        "  2. [cyan]输入问题[/cyan] (如 '方案的核心架构是什么'): 自动检索并带准确出处回答\n"
        "  3. [cyan]make-doc <主题>[/cyan]: 基于知识库逆向总结并生成排版好的 Word 文档\n"
        "  4. [cyan]make-ppt <主题>[/cyan]: 基于知识库逆向提炼并生成 16:9 现代版式 PPT\n"
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

            # 退出命令
            if user_input.lower() in ("exit", "quit", "q"):
                if HAS_RICH:
                    console.print("[dim]👋 再见！知识库已妥善保存。[/dim]")
                else:
                    print("再见！")
                break

            # 查看文件清单
            elif user_input.lower() in ("list", "ls", "查看文件"):
                show_documents_table(agent)

            # 生成 Word
            elif user_input.startswith("make-doc ") or user_input.startswith("生成doc "):
                topic = user_input.split(" ", 1)[1]
                handle_make_doc(agent, topic)

            # 生成 PPT
            elif user_input.startswith("make-ppt ") or user_input.startswith("生成ppt "):
                topic = user_input.split(" ", 1)[1]
                handle_make_ppt(agent, topic)

            # 自动识别是否为文件路径输入
            elif user_input.lower().endswith((".pptx", ".docx")) or Path(user_input.strip('"\'')).is_file():
                handle_ingest(agent, user_input)

            # 默认为问答指令
            else:
                handle_ask(agent, user_input)

        except KeyboardInterrupt:
            print("\n会话已终止。")
            break
        except Exception as e:
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
