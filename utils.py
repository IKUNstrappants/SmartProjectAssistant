import os
import chardet
from pathlib import Path
import fnmatch


def parse_gitignore(root_dir):
    """
    解析项目中的.gitignore文件，返回需要忽略的模式列表
    """
    gitignore_path = os.path.join(root_dir, '.gitignore')
    ignore_patterns = []

    if os.path.exists(gitignore_path):
        with open(gitignore_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    ignore_patterns.append(line)

    # 添加默认忽略的目录
    ignore_patterns.extend(['.git', '.aide_doc', 'build.spec', 'requirements.txt'])
    return ignore_patterns


def should_ignore(path, ignore_patterns):
    """
    检查路径是否应该被忽略
    """
    path = Path(path)
    for pattern in ignore_patterns:
        # 处理目录模式 (以/结尾)
        if pattern.endswith('/'):
            dir_pattern = pattern.rstrip('/')
            if fnmatch.fnmatch(path.name, dir_pattern) or \
                    any(fnmatch.fnmatch(part, dir_pattern) for part in path.parts):
                return True
        # 处理普通模式
        elif fnmatch.fnmatch(path.name, pattern) or \
                any(fnmatch.fnmatch(part, pattern) for part in path.parts):
            return True
    return False


def scan_project_files(root_dir, text_extensions=None):
    """
    递归扫描项目目录，读取所有文本文件内容并返回字典
    自动忽略 .gitignore 中指定的文件和目录

    参数:
        root_dir (str): 项目根目录路径
        text_extensions (list): 要处理的文本文件扩展名列表

    返回:
        dict: {相对文件路径: 文件内容} 的字典
    """
    file_dict = {}
    root_dir = os.path.abspath(root_dir)
    ignore_patterns = parse_gitignore(root_dir)

    for root, dirs, files in os.walk(root_dir, topdown=True):
        # 修改dirs列表以确保不进入被忽略的目录
        dirs[:] = [d for d in dirs if not should_ignore(os.path.join(root, d), ignore_patterns)]

        for file in files:
            file_path = os.path.join(root, file)
            rel_path = os.path.relpath(file_path, root_dir)

            # 检查文件是否应该被忽略
            if should_ignore(rel_path, ignore_patterns):
                continue

            # 检查文件扩展名
            _, ext = os.path.splitext(file)
            if text_extensions is not None and ext.lower() not in text_extensions:
                continue

            try:
                # 自动检测文件编码
                with open(file_path, 'rb') as f:
                    raw_data = f.read()
                    encoding = chardet.detect(raw_data)['encoding'] or 'utf-8'

                # 使用检测到的编码读取文件内容
                with open(file_path, 'r', encoding=encoding, errors='replace') as f:
                    content = f.read()

                # 统一使用当前操作系统的分隔符格式
                normalized_path = os.path.normpath(rel_path)
                file_dict[normalized_path] = content

            except Exception as e:
                print(f"无法读取文件 {file_path}: {str(e)}")

    return file_dict