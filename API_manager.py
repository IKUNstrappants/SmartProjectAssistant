import json
import os
import hashlib
from typing import Dict

import chardet
from openai import OpenAI

from utils import scan_project_files


class API_manager:
    def __init__(self, assistant_api_key: str, summarizer_api_key: str = None,
                 base_url: str = "https://api.deepseek.com",
                 project_root: os.path = None, model: str = "deepseek-chat", file_types = None):
        self.assistant_api_key = assistant_api_key
        if summarizer_api_key is None:
            summarizer_api_key = assistant_api_key
        self.summarizer_api_key = summarizer_api_key
        self.base_url = base_url
        self.model = model
        self.assistant = OpenAI(api_key=self.assistant_api_key, base_url=self.base_url)
        self.summarizer = OpenAI(api_key=self.summarizer_api_key, base_url=self.base_url)
        self.project_root = project_root

        if file_types is None:
            self.file_types = [
                '.txt', '.py', '.js', '.java', '.c', '.cpp', '.h',
                '.html', '.css', '.json', '.xml', '.yml', '.yaml',
                '.md', '.ini', '.conf', '.sh', '.bat' #, '.csv'
            ]
        else:
            self.file_types = file_types

        self.cached_files = {}
        self.summary = {}

        # 添加摘要存储相关的设置
        self.summary_base_dir = os.path.join(project_root, ".aide_doc/summaries") if project_root else None
        self.summary_index_file = os.path.join(project_root, ".aide_doc/summary_index.json") if project_root else None

        # 初始化时尝试加载已有的摘要
        self.load_summary()

    def change_root(self, new_root: str):
        self.project_root = new_root
        self.summary_base_dir = os.path.join(new_root, ".aide_doc/summaries")
        self.summary_index_file = os.path.join(new_root, ".aide_doc/summary_index.json")
        # 重新加载新位置的摘要
        self.load_summary()

    def change_valid_file_types(self, new_types: [str]):
        self.file_types = new_types

    def change_model(self, model: str = None) -> None:
        if model is None:
            self.model = "deepseek-chat" if self.model == "deepseek-reasoner" else "deepseek-reasoner"
        else:
            self.model = model

    def calculate_file_hash(self, content: str) -> str:
        """计算文件内容的哈希值"""
        return hashlib.md5(content.encode('utf-8')).hexdigest()

    def load_summary(self):
        """从文件加载摘要索引和内容"""
        if not self.summary_base_dir or not self.summary_index_file:
            return

        # 确保目录存在
        os.makedirs(self.summary_base_dir, exist_ok=True)

        # 加载索引文件
        self.summary_index = {}
        if os.path.exists(self.summary_index_file):
            try:
                with open(self.summary_index_file, 'r', encoding='utf-8') as f:
                    self.summary_index = json.load(f)
                    print(f"已加载摘要索引，包含 {len(self.summary_index)} 个文件")
            except Exception as e:
                print(f"无法加载摘要索引文件: {str(e)}")
                self.summary_index = {}
        else:
            self.summary_index = {}

        # 从摘要文件加载内容
        self.summary = {}
        for rel_path, data in self.summary_index.items():
            # 构建摘要文件路径（保持原目录结构）
            summary_path = os.path.join(self.summary_base_dir, rel_path + ".summary.txt")
            summary_dir = os.path.dirname(summary_path)
            if not os.path.exists(summary_dir):
                os.makedirs(summary_dir, exist_ok=True)

            if os.path.exists(summary_path):
                try:
                    with open(summary_path, 'r', encoding='utf-8') as f:
                        self.summary[rel_path] = f.read()
                except Exception as e:
                    print(f"无法读取摘要文件 {summary_path}: {str(e)}")

    def save_summary(self):
        """保存摘要索引和内容到文件"""
        if not self.summary_base_dir or not self.summary_index_file:
            return

        # 确保目录存在
        os.makedirs(self.summary_base_dir, exist_ok=True)

        # 保存摘要索引
        try:
            with open(self.summary_index_file, 'w', encoding='utf-8') as f:
                json.dump(self.summary_index, f, indent=2, ensure_ascii=False)
            print(f"已保存摘要索引到 {self.summary_index_file}")
        except Exception as e:
            print(f"保存摘要索引失败: {str(e)}")

        # 保存摘要内容（保持相对路径结构）
        for rel_path, summary_text in self.summary.items():
            if rel_path not in self.summary_index:
                continue

            # 构建摘要文件路径
            summary_path = os.path.join(self.summary_base_dir, rel_path + ".summary.txt")
            summary_dir = os.path.dirname(summary_path)

            # 确保目录存在
            if not os.path.exists(summary_dir):
                os.makedirs(summary_dir, exist_ok=True)

            try:
                with open(summary_path, 'w', encoding='utf-8') as f:
                    f.write(summary_text)
            except Exception as e:
                print(f"保存摘要到文件 {summary_path} 失败: {str(e)}")

    def update_summary(self, update_cache: Dict[str, str], force_reload = False) -> dict:
        """更新摘要并自动保存到文件"""
        new_summary = {}

        for rel_path, content in update_cache.items():
            current_hash = self.calculate_file_hash(content)

            # 检查文件是否已存在且未修改
            existing_hash = self.summary_index.get(rel_path, {}).get("hash", "")
            if (not force_reload) and existing_hash == current_hash:
                # 文件未修改，使用现有摘要
                if rel_path in self.summary:
                    new_summary[rel_path] = self.summary[rel_path]
                continue
            print("更新【"+rel_path+"】的摘要：")
            # 生成新的摘要
            try:
                new_summary[rel_path] = self.simple_talk(
                    system_content="这是一个代码文件：" + content,
                    user_content="总结这个文件，总字数控制在300字以内，不要使用markdown格式。如果是代码文件，分析并总结代码内容，简洁地列出其实现的功能与继承关系；如果是脚本文件，详细说明其指令内容及如何运行。总字数控制在300字以内，不要使用markdown格式。",
                    agent=self.summarizer,
                    model="deepseek-chat"
                )
                print(new_summary[rel_path])

                # 更新摘要索引
                self.summary_index[rel_path] = {
                    "hash": current_hash,
                    "modified": False  # 表示文件已处理
                }
            except Exception as e:
                print(f"生成摘要失败({rel_path}): {str(e)}")
                continue

        # 更新内存中的摘要
        self.summary.update(new_summary)

        # 保存到文件系统
        self.save_summary()

        return new_summary

    def simple_talk(self, system_content: str, user_content: str, history_messages: list = None, agent=None,model=None) -> str:
        if len(system_content) > 65000:
            system_content = system_content[:65000]
        if agent is None:
            agent = self.assistant
        if model is None:
            model = self.model
        if history_messages is None:
            history_messages = []
        messages = [{"role": "system", "content": system_content}] + history_messages
        messages.append({"role": "user", "content": user_content})
        response = agent.chat.completions.create(model=model,messages=messages,stream=False)
        print("response: ")
        print(response.choices[0].message.content)
        return response.choices[0].message.content

    def analyze(self, user_input: str, chat_history, scan_files: bool = None, load_files: bool = None):
        if scan_files is None:
            if len(self.summary.keys()) == 0:
                scan_files = True
            else:
                scan_files = False
        project_content = ""
        if scan_files:
            # 项目根目录检查
            if not self.project_root or not os.path.isdir(self.project_root):
                return "错误：未设置有效项目根目录"

            text_files = scan_project_files(self.project_root, text_extensions=self.file_types)
            modified_files = {}

            # 对比缓存文件
            for rel_path, content in text_files.items():
                if rel_path in self.summary_index and self.summary_index[rel_path]['hash'] == self.calculate_file_hash(content):
                    continue
                modified_files[rel_path] = content

            self.cached_files = text_files
            # 更新摘要
            if modified_files:
                self.update_summary(modified_files)
                print(f"已更新 {len(modified_files)} 个文件的摘要")
        # 构建项目内容概述
        for key, value in self.summary.items():
            project_content += f"[{key}]:\n{value}\n-----\n"
        print(f"已加载 {len(self.summary)} 个文件的摘要")

        if load_files:
            user_input_temp = user_input + "\n\n只列出回答我的问题所需要参考的关键项目代码文件（最多5个，越少越好）的相对路径，路径前后不要加上\"和\"，第一个路径前加上[, 最后一个路径后加上]，以\",\"分隔。示例格式：\"[\\relpath\\A.py,\\relpath\\B.java]\""
            system_prompt = "以下是项目文件的信息概览：\n" + project_content + "\n请根据以上信息回答用户的问题。"
            file_pths = self.simple_talk(system_content=system_prompt, history_messages=chat_history, user_content=user_input_temp, agent=self.assistant, model="deepseek-chat")
            file_pths = [file.strip() for file in file_pths.split("[")[1].split("]")[0].split(",")]
            if len(file_pths) > 5: file_pths = file_pths[:5]
            print(file_pths)
            user_input += "\n以下是参考用的项目代码文件：\n"
            for file in file_pths:
                file_path = os.path.join(self.project_root, file)
                try:
                    with open(file_path, 'rb') as f:
                        raw_data = f.read()
                        encoding = chardet.detect(raw_data)['encoding'] or 'utf-8'
                    # 使用检测到的编码读取文件内容
                    with open(file_path, 'r', encoding=encoding, errors='replace') as f:
                        content = f.read()
                        user_input += file + ": \n" + content + "\n\n"
                except Exception as e:
                    user_input += f"{file}:文件读取失败: {str(e)}\n"
            system_prompt = "以下是项目文件的信息概览：\n" + project_content + "\n请根据以上信息回答用户的问题。"
            return self.simple_talk(system_content=system_prompt, history_messages=chat_history,
                                    user_content=user_input, agent=self.assistant), file_pths
        else:
            system_prompt = "以下是项目文件的信息概览：\n" + project_content + "\n请根据以上信息回答用户的问题。"
            return self.simple_talk(system_content=system_prompt, history_messages=chat_history, user_content=user_input, agent=self.assistant), []