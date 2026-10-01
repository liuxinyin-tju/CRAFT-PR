#!/usr/bin/env python3
"""
Git操作和patch应用工具
"""

import os
import re
import subprocess
import tempfile
from pathlib import Path
import shutil


class GitOperations:
    def __init__(self, repo_path):
        """
        初始化Git操作

        Args:
            repo_path: Git仓库路径
        """
        self.repo_path = Path(repo_path).resolve()
        self.original_branch = None
        self.original_head = None

    def save_current_state(self):
        """保存当前状态"""
        try:
            # 获取当前分支
            result = subprocess.run(
                ['git', 'branch', '--show-current'],
                cwd=self.repo_path,
                capture_output=True,
                text=True
            )
            self.original_branch = result.stdout.strip() or 'main'

            # 获取当前HEAD
            result = subprocess.run(
                ['git', 'rev-parse', 'HEAD'],
                cwd=self.repo_path,
                capture_output=True,
                text=True
            )
            self.original_head = result.stdout.strip()

            print(f"保存当前状态: 分支={self.original_branch}, HEAD={self.original_head[:8]}")
        except subprocess.CalledProcessError as e:
            print(f"保存状态失败: {e}")

    def restore_state(self):
        """恢复原始状态"""
        if self.original_branch:
            try:
                print(f"恢复状态到分支: {self.original_branch}")
                subprocess.run(
                    ['git', 'checkout', '-f', self.original_branch],
                    cwd=self.repo_path,
                    check=True,
                    capture_output=True,
                    text=True
                )
            except subprocess.CalledProcessError as e:
                print(f"恢复分支失败: {e}")
                # 尝试切换到master
                try:
                    subprocess.run(
                        ['git', 'checkout', 'main'],
                        cwd=self.repo_path,
                        check=True,
                        capture_output=True,
                        text=True
                    )
                except:
                    pass

    def checkout_sha(self, sha):
        """
        切换到指定的SHA

        Args:
            sha: 提交哈希值

        Returns:
            bool: 是否成功
        """
        try:
            # 先尝试获取提交信息，确认SHA存在
            subprocess.run(
                ['git', 'show', sha, '--quiet'],
                cwd=self.repo_path,
                check=True,
                capture_output=True,
                text=True
            )

            # 切换到指定SHA（分离头指针状态）
            # print(f"正在切换到SHA: {sha[:8]}")
            result = subprocess.run(
                ['git', 'checkout', '-f', sha],
                cwd=self.repo_path,
                check=True,
                capture_output=True,
                text=True
            )
            
            subprocess.run(
                ['git', 'clean', '-fd'],
                cwd=self.repo_path,
                check=True,
                capture_output=True,
                text=True
            )

            # print(f"成功切换到SHA: {sha[:8]}")
            return True

        except subprocess.CalledProcessError as e:
            print(f"切换到SHA失败 {sha[:8]}: {e}")
            if e.stderr:
                print(f"错误信息: {e.stderr[:200]}")

            # 尝试fetch后重试
            try:
                print("尝试fetch最新代码...")
                subprocess.run(
                    ['git', 'fetch', 'origin'],
                    cwd=self.repo_path,
                    check=True,
                    capture_output=True,
                    text=True
                )

                # 再次尝试
                result = subprocess.run(
                    ['git', 'checkout', sha],
                    cwd=self.repo_path,
                    check=True,
                    capture_output=True,
                    text=True
                )
                print(f"通过fetch后成功切换到SHA: {sha[:8]}")
                return True

            except subprocess.CalledProcessError as e2:
                print(f"即使fetch后也无法切换到SHA {sha[:8]}: {e2}")
                return False

    def apply_patch(self, patch_content, file_path=None, ignore_whitespace=False):
        """
        应用patch

        Args:
            patch_content: patch内容
            file_path: 可选，指定应用到的文件路径
            ignore_whitespace: 是否忽略空白字符

        Returns:
            bool: 是否成功
        """
        # 创建临时patch文件
        with tempfile.NamedTemporaryFile(mode='w', suffix='.patch', delete=False) as f:
            f.write(patch_content)
            patch_file = f.name

        try:
            # 应用patch
            cmd = ['git', 'apply']
            if ignore_whitespace:
                cmd.append('--ignore-whitespace')

            if file_path:
                cmd.extend(['--include', file_path])

            cmd.append(patch_file)

            result = subprocess.run(
                cmd,
                cwd=self.repo_path,
                check=True,
                capture_output=True,
                text=True
            )

            # print(f"成功应用patch")
            return True

        except subprocess.CalledProcessError as e:
            print(f"应用patch失败: {e}")
            if e.stderr:
                print(f"错误信息: {e.stderr[:200]}")

            # 如果失败，尝试使用--reject选项
            try:
                print("尝试使用--reject选项...")
                cmd = ['git', 'apply', '--reject']
                if ignore_whitespace:
                    cmd.append('--ignore-whitespace')
                cmd.append(patch_file)

                result = subprocess.run(
                    cmd,
                    cwd=self.repo_path,
                    check=False,
                    capture_output=True,
                    text=True
                )

                if result.returncode == 0:
                    print("使用--reject后成功应用patch（可能有部分冲突）")
                    return True
                else:
                    print("即使使用--reject也无法应用patch")
                    return False

            except Exception as e2:
                print(f"使用--reject也失败: {e2}")
                return False

        finally:
            # 删除临时文件
            try:
                os.unlink(patch_file)
            except:
                pass

    def create_temporary_branch(self, sha, branch_name=None):
        """
        创建临时分支并切换到指定SHA

        Args:
            sha: 提交哈希值
            branch_name: 分支名，如果为None则自动生成

        Returns:
            str: 分支名
        """
        if branch_name is None:
            import time
            branch_name = f"temp_analysis_{int(time.time())}"

        try:
            # 创建临时分支
            subprocess.run(
                ['git', 'checkout', '-b', branch_name, sha],
                cwd=self.repo_path,
                check=True,
                capture_output=True,
                text=True
            )

            print(f"创建并切换到临时分支: {branch_name} (基于SHA: {sha[:8]})")
            return branch_name

        except subprocess.CalledProcessError as e:
            print(f"创建临时分支失败: {e}")
            # 尝试先切换到SHA再创建分支
            try:
                subprocess.run(
                    ['git', 'checkout', sha],
                    cwd=self.repo_path,
                    check=True,
                    capture_output=True,
                    text=True
                )

                subprocess.run(
                    ['git', 'checkout', '-b', branch_name],
                    cwd=self.repo_path,
                    check=True,
                    capture_output=True,
                    text=True
                )

                print(f"创建并切换到临时分支: {branch_name}")
                return branch_name

            except subprocess.CalledProcessError as e2:
                print(f"备选方案也失败: {e2}")
                raise

    def cleanup_temporary_branch(self, branch_name):
        """
        清理临时分支

        Args:
            branch_name: 分支名
        """
        try:
            # 切换到其他分支
            subprocess.run(
                ['git', 'checkout', self.original_branch or 'main'],
                cwd=self.repo_path,
                check=True,
                capture_output=True,
                text=True
            )

            # 删除临时分支
            subprocess.run(
                ['git', 'branch', '-D', branch_name],
                cwd=self.repo_path,
                check=True,
                capture_output=True,
                text=True
            )

            print(f"已删除临时分支: {branch_name}")

        except subprocess.CalledProcessError as e:
            print(f"清理临时分支失败 {branch_name}: {e}")

    def get_file_content_at_sha(self, file_path, sha):
        """
        获取指定SHA下的文件内容

        Args:
            file_path: 文件路径（相对路径）
            sha: 提交哈希值

        Returns:
            str: 文件内容，如果失败返回None
        """
        try:
            result = subprocess.run(
                ['git', 'show', f'{sha}:{file_path}'],
                cwd=self.repo_path,
                check=True,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='ignore'
            )

            return result.stdout

        except subprocess.CalledProcessError as e:
            print(f"获取文件内容失败 {file_path}@{sha[:8]}: {e}")
            return None

    def get_modified_files_in_patch(self, patch_content):
        """
        从patch内容中提取修改的文件列表

        Args:
            patch_content: patch内容

        Returns:
            list: 修改的文件路径列表（相对路径）
        """
        modified_files = []

        lines = patch_content.split('\n')
        i = 0
        while i < len(lines):
            if lines[i].startswith('diff --git'):
                # 格式: diff --git a/path/to/file b/path/to/file
                match = re.search(r'b/(.*)$', lines[i])
                if match:
                    file_path = match.group(1)
                    modified_files.append(file_path)

                    # 跳过这个文件的patch内容
                    i += 1
                    while i < len(lines) and not lines[i].startswith('diff --git'):
                        i += 1
                    continue

            i += 1

        return modified_files

    def get_file_diff_at_line(self, file_path, patch_content, line_number):
        """
        获取指定文件在patch中的某行差异

        Args:
            file_path: 文件路径
            patch_content: patch内容
            line_number: 行号（1-based，在patch中的行号）

        Returns:
            tuple: (diff_type, content)
                   diff_type: '+'表示添加，'-'表示删除，' '表示不变
        """
        # 找到指定文件的patch部分
        lines = patch_content.split('\n')
        in_target_file = False
        file_patch_lines = []

        i = 0
        while i < len(lines):
            if lines[i].startswith('diff --git'):
                match = re.search(r'b/(.*)$', lines[i])
                if match and match.group(1) == file_path:
                    in_target_file = True
                    i += 1
                    continue
                elif match:
                    in_target_file = False

            if in_target_file:
                file_patch_lines.append(lines[i])

            i += 1

        # 在文件的patch中查找指定行
        if line_number - 1 < len(file_patch_lines):
            line = file_patch_lines[line_number - 1]
            if line.startswith('+'):
                return ('+', line[1:])
            elif line.startswith('-'):
                return ('-', line[1:])
            elif line.startswith(' '):
                return (' ', line[1:])

        return None

