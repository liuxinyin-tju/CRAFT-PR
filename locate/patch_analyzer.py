#!/usr/bin/env python3
"""
Patch分析和文件定位工具
"""

import re
import os
from pathlib import Path


class PatchAnalyzer:
    def __init__(self):
        pass

    def parse_patch(self, patch_content):
        """
        解析patch内容，提取详细信息

        Returns:
            dict: 包含解析信息的字典
        """
        files_info = []
        lines = patch_content.split('\n')

        i = 0
        while i < len(lines):
            if lines[i].startswith('diff --git'):
                file_info = {
                    'raw_diff_line': lines[i],
                    'hunks': []
                }

                # 提取文件路径
                match_a = re.search(r'\sa/(.*?)\s', lines[i])
                match_b = re.search(r'\sb/(.*?)$', lines[i])
                if match_a:
                    file_info['file_a'] = match_a.group(1)
                if match_b:
                    file_info['file_b'] = match_b.group(1)

                print(file_info['file_b'])
                i += 1

                # 查找index行（可选）
                if i < len(lines) and lines[i].startswith('index '):
                    file_info['index_line'] = lines[i]
                    i += 1

                # 查找---和+++行
                if i < len(lines) and lines[i].startswith('--- '):
                    file_info['from_file'] = lines[i]
                    i += 1
                if i < len(lines) and lines[i].startswith('+++ '):
                    file_info['to_file'] = lines[i]
                    i += 1

                # 解析hunks
                while i < len(lines) and not lines[i].startswith('diff --git'):
                    if lines[i].startswith('@@ '):
                        hunk_info = self._parse_hunk(lines[i])
                        hunk_lines = []

                        i += 1
                        while i < len(lines) and not lines[i].startswith('@@') and not lines[i].startswith('diff --git'):
                            hunk_lines.append(lines[i])
                            i += 1

                        hunk_info['lines'] = hunk_lines
                        file_info['hunks'].append(hunk_info)
                    else:
                        i += 1

                files_info.append(file_info)
            else:
                i += 1

        return files_info

    def _parse_hunk(self, hunk_line):
        """
        解析hunk行

        Args:
            hunk_line: @@行

        Returns:
            dict: hunk信息
        """
        # 格式: @@ -start_a,lines_a +start_b,lines_b @@ 可选的上下文
        pattern = r'@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)'
        match = re.match(pattern, hunk_line)

        if match:
            start_a = int(match.group(1))
            lines_a = int(match.group(2) or 1)
            start_b = int(match.group(3))
            lines_b = int(match.group(4) or 1)
            context = match.group(5).strip()

            return {
                'raw': hunk_line,
                'start_a': start_a,
                'lines_a': lines_a,
                'start_b': start_b,
                'lines_b': lines_b,
                'context': context
            }

        return {'raw': hunk_line}

    def locate_modifications(self, file_path, patch_content):
        """
        定位patch中的修改位置（更精确的版本）

        Args:
            file_path: 文件路径
            patch_content: patch内容

        Returns:
            list: 修改位置，格式为[(start_line, end_line, change_type), ...]
        """
        modifications = []

        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                file_content = f.read()

            # 解析patch
            files_info = self.parse_patch(patch_content)

            for file_info in files_info:
                if file_info.get('file_b') != str(Path(file_path).relative_to(Path(file_path).parents[1])):
                    continue

                for hunk_info in file_info['hunks']:
                    hunk_mods = self._locate_hunk_modifications(file_content, hunk_info)
                    modifications.extend(hunk_mods)

        except Exception as e:
            print(f"定位修改失败 {file_path}: {e}")

        return modifications

    def _locate_hunk_modifications(self, file_content, hunk_info):
        """
        定位单个hunk的修改位置

        Args:
            file_content: 文件内容
            hunk_info: hunk信息

        Returns:
            list: 修改位置
        """
        modifications = []

        file_lines = file_content.split('\n')
        hunk_lines = hunk_info['lines']

        # 提取上下文行（以空格开头的行）
        context_lines = []
        for line in hunk_lines:
            if line.startswith(' '):
                context_lines.append(line[1:])  # 移除前导空格

        if not context_lines:
            # 如果没有明确的上下文，使用hunk起始位置
            start_line = hunk_info['start_b'] - 1  # 转换为0-based
            return [(start_line, start_line + hunk_info.get('lines_b', 1), 'unknown')]

        # 在文件中查找最佳匹配
        best_match = self._find_context_match(file_lines, context_lines, hunk_info['start_b'] - 1)

        if best_match is not None:
            # 分析hunk中的修改类型
            current_pos = best_match
            for line in hunk_lines:
                if line.startswith('+'):
                    # 添加行
                    modifications.append((current_pos, current_pos, 'addition'))
                elif line.startswith('-'):
                    # 删除行
                    modifications.append((current_pos, current_pos, 'deletion'))
                elif line.startswith(' '):
                    # 上下文行，移动到下一行
                    current_pos += 1

        return modifications

    def _find_context_match(self, file_lines, context_lines, expected_start):
        """
        在文件中查找上下文匹配

        Args:
            file_lines: 文件行列表
            context_lines: 上下文行列表
            expected_start: 期望的起始位置（0-based）

        Returns:
            int: 最佳匹配位置，如果没有找到返回None
        """
        if not context_lines:
            return expected_start

        # 预处理上下文行（去除空白）
        clean_context = [line.strip() for line in context_lines]

        # 搜索范围
        search_window = 100  # 搜索窗口大小
        start_search = max(0, expected_start - search_window)
        end_search = min(len(file_lines), expected_start + search_window + len(context_lines))

        best_score = 0
        best_position = None

        for i in range(start_search, end_search - len(clean_context) + 1):
            # 提取文件片段
            file_slice = [line.strip() for line in file_lines[i:i+len(clean_context)]]

            # 计算相似度
            score = self._calculate_context_similarity(clean_context, file_slice)

            if score > best_score:
                best_score = score
                best_position = i

        # 设置阈值
        if best_score > 0.8:
            return best_position
        elif best_score > 0.5:
            print(f"  警告: 上下文匹配分数较低 ({best_score:.2f})，可能位置不准确")

        return best_position if best_score > 0.5 else expected_start

    def _calculate_context_similarity(self, context_lines, file_lines):
        """
        计算上下文相似度

        Args:
            context_lines: 上下文行列表
            file_lines: 文件行列表

        Returns:
            float: 相似度分数（0-1）
        """
        if len(context_lines) != len(file_lines):
            return 0

        matches = 0
        total = len(context_lines)

        for i in range(total):
            # 简单的字符串相等匹配
            if context_lines[i] == file_lines[i]:
                matches += 1
            # 或者部分匹配（包含关系）
            elif context_lines[i] and file_lines[i] and (context_lines[i] in file_lines[i] or file_lines[i] in context_lines[i]):
                matches += 0.5

        return matches / total

    def extract_modified_lines_from_hunk(self, hunk_info):
        """
        从hunk中提取具体修改的行

        Args:
            hunk_info: hunk信息

        Returns:
            dict: 添加行和删除行的信息
        """
        added_lines = []
        deleted_lines = []

        if 'lines' not in hunk_info:
            return {'added': added_lines, 'deleted': deleted_lines}

        current_line_b = hunk_info['start_b']  # 新文件中的行号（1-based）

        for line in hunk_info['lines']:
            if line.startswith('+'):
                # 添加的行（在新文件中）
                added_lines.append({
                    'line_number': current_line_b,
                    'content': line[1:]
                })
                current_line_b += 1
            elif line.startswith('-'):
                # 删除的行（在旧文件中）
                deleted_lines.append({
                    'content': line[1:]
                })
                # 删除行不影响新文件的行号
            elif line.startswith(' '):
                # 未修改的行
                current_line_b += 1

        return {
            'added': added_lines,
            'deleted': deleted_lines,
            'hunk_start': hunk_info['start_b']
        }

    def get_modification_context(self, file_path, line_number, context_lines=5):
        """
        获取修改位置的上下文

        Args:
            file_path: 文件路径
            line_number: 行号（1-based）
            context_lines: 上下文行数

        Returns:
            dict: 上下文信息
        """
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()

            line_number_idx = line_number - 1  # 转换为0-based
            start = max(0, line_number_idx - context_lines)
            end = min(len(lines), line_number_idx + context_lines + 1)

            return {
                'before': lines[start:line_number_idx],
                'line': lines[line_number_idx] if line_number_idx < len(lines) else '',
                'after': lines[line_number_idx+1:end],
                'line_number': line_number,
                'start_line': start + 1,
                'end_line': end
            }

        except Exception as e:
            print(f"获取上下文失败 {file_path}:{line_number}: {e}")
            return None

