import json
import sys

import gradio as gr
from gradio.components.chatbot import ChatMessage

from API_manager import API_manager
import time
import os

# 添加打包后资源路径处理
if getattr(sys, 'frozen', False):
    # 打包后的可执行文件路径
    BASE_DIR = os.path.dirname(sys.executable)
else:
    # 开发环境路径
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 修改历史记录路径
PROJECTS_HISTORY_DIR = os.path.join(BASE_DIR, "history_information")
os.makedirs(PROJECTS_HISTORY_DIR, exist_ok=True)
PROJECTS_HISTORY_FILE = os.path.join(PROJECTS_HISTORY_DIR, "projects_history.json")


# API管理器实例
api_manager: API_manager = None

PROJECTS_HISTORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "history_information/projects_history.json")

def initialize_manager(api_key_assistant, api_key_summarize, project_root, file_types, model_choice, load_history=True):
    """初始化API管理器"""
    global api_manager

    # 如果选择了加载历史配置
    if load_history and project_root:
        try:
            project_path = os.path.abspath(project_root)
            projects_history = load_projects_history()
            history = projects_history.get(project_path)

            if history:
                # 使用历史配置
                api_key_assistant = history["assistant_api_key"]
                api_key_summarize = history["summarizer_api_key"]
                file_types = ",".join(history["file_types"])
        except Exception as e:
            print(f"加载历史配置失败: {str(e)}")

    if not api_key_assistant.strip() or not api_key_summarize.strip():
        return "错误：必须提供API密钥", {}

    if not project_root or not os.path.exists(project_root):
        return "错误：项目目录不存在", {}

    try:
        if api_manager is None:
            api_manager = API_manager(
                assistant_api_key=api_key_assistant,
                summarizer_api_key=api_key_summarize,
                project_root=project_root,
                file_types=[ft.strip() for ft in file_types.split(",")] if file_types.strip() else None,
                model=model_choice
            )
            print("API管理器初始化成功")
            status = "API管理器初始化成功"
        else:
            api_manager.change_root(project_root)
            api_manager.change_valid_file_types([ft.strip() for ft in file_types.split(",")])
            api_manager.change_model(model_choice)
            status = "设置已更新"

        file_count = len(api_manager.summary_index) if hasattr(api_manager, 'summary_index') else 0

        # 准备预览数据（确保返回字典格式）
        preview = {"状态": status, "已加载文件数": file_count}
        if file_count > 0:
            preview["示例文件"] = list(api_manager.summary_index.keys())[0]
        print("preview:", preview)
        save_project_to_history(project_root, api_key_assistant, api_key_summarize, file_types)
        return f"{status} | 已加载{file_count}个文件摘要", [list(api_manager.summary_index.keys()).__str__(), status]
    except Exception as e:
        return f"初始化失败: {str(e)}", {}

def load_projects_history():
    """加载项目历史记录"""
    if os.path.exists(PROJECTS_HISTORY_FILE):
        try:
            with open(PROJECTS_HISTORY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"无法加载项目历史记录: {str(e)}")
    return {}


def save_project_to_history(project_root, api_key_assistant, api_key_summarize, file_types):
    """将当前项目保存到历史记录"""
    if not project_root:
        return

    projects_history = load_projects_history()
    project_path = os.path.abspath(project_root)

    projects_history[project_path] = {
        "assistant_api_key": api_key_assistant,
        "summarizer_api_key": api_key_summarize,
        "file_types": [ft.strip() for ft in file_types.split(",")] if file_types.strip() else [],
        "last_used": time.strftime("%Y-%m-%d %H:%M:%S")
    }

    try:
        with open(PROJECTS_HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(projects_history, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"保存项目历史记录失败: {str(e)}")

def chat_with_ai(message, chat_history, scan_files, load_files):
    """处理用户聊天请求并返回AI响应"""
    if api_manager is None:
        return "请先初始化API设置！"

    try:
        start_time = time.time()
        response, extra = api_manager.analyze(user_input=message, chat_history=chat_history, scan_files=scan_files, load_files=load_files)
        elapsed = time.time() - start_time

        file_count = len(api_manager.summary) if hasattr(api_manager, 'summary') else 0
        status = f"\n\n[统计] 响应时间: {elapsed:.2f}s | 文件摘要数: {file_count}"
        if load_files:
            status += f" | 读取代码文件：{extra}"

        return response + status
    except Exception as e:
        return f"请求处理失败: {str(e)}"

# 创建界面
with gr.Blocks(title="智能API助手", theme=gr.themes.Soft()) as demo:
    gr.Markdown("# 🚀 智能项目助手控制面板")

    # 持久化存储状态
    api_key_state = gr.State()
    project_root_state = gr.State()

    # API配置面板
    with gr.Tab("API配置"):
        with gr.Row():
            with gr.Column(scale=1):
                gr.Markdown("### 基本设置")
                api_key_assistant = gr.Textbox(
                    label="API密钥01",
                    type="password",
                    placeholder="输入您的DeepSeek API密钥"
                )
                api_key_summarize = gr.Textbox(
                    label="API密钥02",
                    type="password",
                    placeholder="输入您的DeepSeek API密钥"
                )

                project_root = gr.Textbox(
                    label="项目根目录",
                    placeholder="项目根目录的绝对路径"
                )

                file_types = gr.Textbox(
                    label="文件类型 (逗号分隔)",
                    value='.txt,.py,.js,.java,.c,.cpp,.h,.html,.css,.json,.xml,.yml,.yaml,.md,.ini,.conf,.sh,.bat',
                    placeholder=".java,.py"
                )

                model_choice = gr.Radio(
                    choices=["deepseek-chat", "deepseek-reasoner"],
                    value="deepseek-chat",
                    label="选择模型"
                )

                config_btn = gr.Button("应用配置", variant="primary")

                load_history = gr.Checkbox(label="加载该项目的历史配置", value=False)
                # 添加历史项目选择下拉框
                history_projects = gr.Dropdown(
                    label="历史项目",
                    choices=[],
                    interactive=True
                )

                # 添加刷新历史项目按钮
                refresh_btn = gr.Button("刷新历史项目", variant="secondary")

            with gr.Column(scale=1):
                gr.Markdown("### 配置状态")
                status_display = gr.Textbox(
                    label="系统状态",
                    value="尚未初始化",
                    interactive=False
                )

                # 使用Dataframe代替JSON组件
                summary_preview = gr.Dataframe(
                    label="摘要预览",
                    headers=["文件路径", "状态"],
                    value=[["配置未初始化", ""]],
                    interactive=False
                )

        with gr.Row():
            scan_btn = gr.Button("扫描项目", variant="secondary")
            reset_btn = gr.Button("重置配置", variant="stop")

    # 聊天助手面板
    with gr.Tab("聊天助手"):
        chatbot = gr.Chatbot(
            label="对话记录",
            height=600,
            type="messages"
        )

        with gr.Row():
            scan_files = gr.Checkbox(label="扫描项目文件，自动更新修改过的文件的摘要", value=False)
            load_files = gr.Checkbox(label="自动拉取相关文件", value=False)

        with gr.Row():
            msg = gr.Textbox(
                placeholder="输入您的问题...",
                show_label=False,
                container=False
            )
            submit_btn = gr.Button("发送", variant="primary")

    # ===== 事件处理 =====

    # 配置按钮处理
    config_btn.click(
        initialize_manager,
        inputs=[api_key_assistant, api_key_summarize, project_root, file_types, model_choice],
        outputs=[status_display, summary_preview]
    )


    # 扫描按钮处理
    def update_summary_preview():
        """更新摘要预览"""
        if api_manager and hasattr(api_manager, 'summary_index'):
            preview_data = [
                [f"{i + 1}. {k[:20]}...", "已加载"]
                for i, k in enumerate(list(api_manager.summary_index.keys())[:10])
            ]
            return "摘要已加载", preview_data
        return "请先配置API设置", [["配置未初始化", ""]]


    scan_btn.click(
        update_summary_preview,
        inputs=[],
        outputs=[status_display, summary_preview]
    )


    # 重置配置
    def reset_config():
        global api_manager
        api_manager = None
        return "配置已重置，请重新设置", [["配置已重置", ""]]


    reset_btn.click(
        reset_config,
        inputs=[],
        outputs=[status_display, summary_preview]
    )


    def handle_chat(message, chat_history, scan_files, load_files):
        # 第一步：添加用户消息和占位符消息，并立即显示
        chat_history += [{"role": "user", "content": message}, {"role": "assistant", "content": "等待响应。。。"}]
        # 立即显示更新后的聊天记录（包含占位符）
        yield chat_history

        # 获取AI响应
        bot_response = chat_with_ai(message, chat_history, scan_files, load_files)

        # 替换占位符为实际响应
        chat_history[-1]["content"] = bot_response
        # 返回更新后的聊天记录
        yield chat_history


    # 添加刷新历史项目的函数
    def refresh_history_projects():
        projects_history = load_projects_history()
        choices = [f"{path} (最后使用: {data['last_used']})" for path, data in projects_history.items()]
        return gr.Dropdown(choices=choices, value=None)


    # 当选择历史项目时自动填充路径
    def on_project_selected(project_path):
        if not project_path:
            return gr.Textbox(value=""), gr.Checkbox(value=False)

        # 提取实际路径（去掉时间戳部分）
        actual_path = project_path.split(" (最后使用:")[0].strip()
        return gr.Textbox(value=actual_path), gr.Checkbox(value=True)


    # 绑定事件
    refresh_btn.click(
        refresh_history_projects,
        inputs=[],
        outputs=[history_projects]
    )

    history_projects.change(
        on_project_selected,
        inputs=[history_projects],
        outputs=[project_root, load_history]
    )

    # 在应用启动时自动加载历史项目
    demo.load(
        refresh_history_projects,
        inputs=[],
        outputs=[history_projects]
    )

    # 绑定聊天事件
    msg.submit(
        handle_chat,
        inputs=[msg, chatbot, scan_files, load_files],
        outputs=[chatbot]
    )

    submit_btn.click(
        handle_chat,
        inputs=[msg, chatbot, scan_files, load_files],
        outputs=[chatbot]
    )

# 启动应用
if __name__ == "__main__":
    demo.launch(
        server_port=7860,
        share=False
    )