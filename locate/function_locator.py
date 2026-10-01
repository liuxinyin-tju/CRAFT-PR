#!/usr/bin/env python3
"""
改进的函数定位器，能够区分新函数创建和原函数修改
"""

import re
import os
from pathlib import Path
from java_parser import JavaParser
from patch_analyzer import PatchAnalyzer

import tree_sitter_java as tsjava
from tree_sitter import Language, Parser

JAVA_LANGUAGE = Language(tsjava.language(), name='java')

parser = Parser()
parser.language = JAVA_LANGUAGE


class ImprovedFunctionLocator:
    """改进的函数定位器，能够区分新函数创建和原函数修改"""

    def __init__(self, project_root=None):
        """
        初始化函数定位器

        Args:
            project_root: 项目根目录路径
        """
        self.project_root = Path(project_root).resolve() if project_root else None
        self.java_parser = JavaParser()
        self.patch_analyzer = PatchAnalyzer()

        # 用于检测方法定义的模式
        self.method_def_pattern = re.compile(
            r'(?:public|protected|private|static|final|synchronized|abstract|native|\s)*'
            r'(?:@\w+(?:\([^)]*\))?\s+)*'  # 注解
            r'(?:\<\w+(?:,\s*\w+)*\>)?\s*'  # 泛型参数
            r'(?:void|boolean|char|byte|short|int|long|float|double|[\w\<\>\[\],\s\.\$]+)\s+'  # 返回类型
            r'(\w+)'  # 方法名 (捕获组)
            r'\s*\([^)]*\)'  # 参数列表
            r'(?:\s*throws\s+[\w\s,\.]+)?'  # throws子句
        )

        # 检测方法体开始的模式
        self.method_body_start = re.compile(r'[\s\S]*\{')

    def analyze_functions_after_patch(self, patch_content, project_path=None):
        """
        分析patch并定位修改的函数，区分新函数和修改的函数

        Args:
            patch_content: patch内容
            base_sha: 基础SHA（可选）
            project_path: 项目路径

        Returns:
            list: 文件-函数对列表 [(file_path, function_name), ...]
        """
        file_function_pairs = []

        # 解析patch获取修改的文件
        files_info = self.patch_analyzer.parse_patch(patch_content)

        print(f"解析到 {len(files_info)} 个文件")

        for file_info in files_info:
            file_path = file_info.get('file_b')
            if not file_path:
                continue

            # print(f"处理文件: {file_path}")

            # 构建完整路径
            full_path = self._get_full_path(file_path, project_path)
            if not full_path:
                print(f"  无法构建完整路径: {file_path}")
                continue

            # 检查文件是否存在
            if not full_path.exists():
                print(f"  文件不存在: {full_path}")
                # 继续处理，因为可能仍然可以通过其他方式分析
                # 例如，文件可能被重命名或移动了
                # 我们暂时跳过这个文件的详细分析
                continue

            # 检查是否是Java文件
            if not file_path.endswith('.java'):
                print(f"  非Java文件: {file_path}，跳过")
                continue

            file_functions = []

            # 分析每个hunk
            for hunk_idx, hunk_info in enumerate(file_info.get('hunks', [])):
                # 获取hunk的详细信息
                hunk_start = hunk_info.get('start_b', 1)
                hunk_lines = hunk_info.get('lines', [])

                print(f"  处理hunk {hunk_idx+1}: 起始行={hunk_start}, 行数={len(hunk_lines)}")

                # 提取hunk中新增的行
                added_lines = []
                for i, line in enumerate(hunk_lines):
                    if line.startswith('+') and not line.startswith('++'):
                        added_lines.append({
                            'content': line[1:],
                            'index': i
                        })

                # print(f"    hunk中新增行数: {len(added_lines)}")

                # 只有有新增行时才分析
                if added_lines:
                    modified_functions = self._find_modified_functions(full_path, hunk_start, hunk_lines)
                    # print(f"    找到修改的函数: {[m['name'] for m in modified_functions]}")
                    for func_info in modified_functions:
                        if func_info['name'] not in [f[1] for f in file_functions]:
                            file_functions.append((file_path, func_info['name'], func_info['start_line']))

            # 添加这个文件的所有函数到总列表
            for file_func in file_functions:
                if file_func not in file_function_pairs:
                    file_function_pairs.append(file_func)

        # print(f"最终找到 {len(file_function_pairs)} 个文件-函数对")
        return file_function_pairs

    def _get_full_path(self, file_path, project_path):
        """获取文件的完整路径，处理路径映射问题"""
        base_path = None
        if project_path:
            base_path = Path(project_path)
        elif self.project_root:
            base_path = self.project_root
        else:
            return Path(file_path)

        # 首先尝试直接路径
        direct_path = base_path / file_path
        if direct_path.exists():
            return direct_path

        # 如果还是不存在，尝试查找文件
        print(f"  文件不存在: {file_path}，在 {base_path} 下")
        # 可以尝试搜索，但为了简单，先返回None
        return direct_path



    def _find_modified_functions(self, file_path, hunk_start, hunk_lines):
        """
        查找被修改的函数（修改已有函数的情况）

        Args:
            file_path: 文件路径
            hunk_start: hunk在新文件中的起始行号
            hunk_lines: hunk的行内容

        Returns:
            list: 被修改的函数信息列表
        """
        # print(f"  查找修改的函数: 文件={file_path}, hunk起始行={hunk_start}")

        # 解析文件获取所有函数
        parse_result = self.java_parser.parse_file(str(file_path))
        if not parse_result:
            print("  解析文件失败")
            return []

        # 确定修改影响的行范围
        # 新文件中受影响的行范围
        current_line = hunk_start
        affected_lines = set()

        for i, line in enumerate(hunk_lines):
            if line.startswith('+'):  # 添加行
                # print(f"    添加行 {current_line}: {line[:50]}...")
                affected_lines.add(current_line)
            # elif line.startswith('-'):  # 删除行
                # print(f"    删除行: {line[:50]}...")
            # 删除行不影响新文件的行号
            current_line += 1 if line.startswith(' ') or line.startswith('+') else 0

        # print(f"  受影响的行号: {sorted(affected_lines)}")

        # 查找包含受影响行的函数
        modified_functions = []

        # 首先获取文件中所有方法的精确范围
        methods_with_ranges = self._get_method_ranges(str(file_path))

        # print(f"  文件中的方法范围:")
        # for method in methods_with_ranges:
        #     print(f"    {method['name']}: {method['start_line']}-{method['end_line']}")

        for method in methods_with_ranges:
            # 检查是否有受影响行在这个方法的范围内
            for line_num in affected_lines:
                if method['start_line'] <= line_num <= method['end_line']:
                    # print(f"    行 {line_num} 在方法 {method['name']} 的范围内")
                    if method not in modified_functions:
                        modified_functions.append(method)
                    break

        # # 如果没有找到，尝试简化的查找逻辑
        # if not modified_functions:
        #     print("  未通过精确范围找到修改的函数，使用简化逻辑")
        #     # 使用原始的逻辑作为备用
        #     for method in parse_result.get('methods', []):
        #         # 简化：只要hunk起始行在方法定义行之后，就认为可能修改了该函数
        #         if method['line'] <= hunk_start:
        #             # 检查是否有更精确的方法（最近的）
        #             print(method)
        #             if not modified_functions or method['line'] > modified_functions[0]['line']:
        #                 modified_functions = [method]
        #             elif method['line'] == modified_functions[0]['line']:
        #                 modified_functions.append(method)

        # print(f"  找到的修改函数: {[m['name'] for m in modified_functions]}")
        return modified_functions


    def _get_method_ranges(self, file_path):
        """
        获取文件中所有方法的起始行和结束行范围

        Args:
            file_path: 文件路径

        Returns:
            list: 方法信息列表，包含name, start_line, end_line
        """
        def extract_method_info(method_node):
            """
            从方法声明节点提取方法信息，包括参数类型
            
            Args:
                method_node: tree-sitter 的方法声明节点
                
            Returns:
                dict: 包含方法名（含参数类型）、起始行、结束行
            """
            # 提取方法名
            method_name_node = method_node.child_by_field_name("name")
            if not method_name_node:
                return None
            method_name = method_name_node.text.decode()
            
            # 提取参数类型
            param_types = []
            parameters_node = method_node.child_by_field_name("parameters")
            if parameters_node:
                # 遍历参数列表中的每个参数
                for child in parameters_node.children:
                    if child.type == 'formal_parameter':
                        # 获取参数的类型节点
                        type_node = child.child_by_field_name("type")
                        if type_node:
                            param_type = type_node.text.decode()
                            param_types.append(param_type)
                    elif child.type == 'spread_parameter':
                        # 可变参数 (如 String... args)
                        type_node = child.child_by_field_name("type")
                        if type_node:
                            param_type = type_node.text.decode() + "..."
                            param_types.append(param_type)
            
            # 组合方法名和参数类型
            if param_types:
                full_method_name = f"{method_name}({','.join(param_types)})"
            else:
                full_method_name = f"{method_name}()"
            
            start_line = method_node.range.start_point.row + 1
            end_line = method_node.range.end_point.row + 1
            
            return {
                'name': full_method_name,
                'start_line': start_line,  # 1-based
                'end_line': end_line  # 1-based
            }
        
        def extract_methods(node):
            """
            从AST中提取方法信息

            Args:
                node: AST根节点

            Returns:
                list: 方法信息列表
            """
            methods = []

            # 递归遍历AST，查找方法声明节点
            if node.type == 'method_declaration':
                method_info = extract_method_info(node)
                if method_info:
                    methods.append(method_info)

            # 遍历所有子节点
            for child in node.children:
                methods.extend(extract_methods(child))

            return methods
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()

            tree = parser.parse(content.encode("utf-8"))
            root = tree.root_node

            methods_with_ranges = extract_methods(root)
                    
            return methods_with_ranges

        except Exception as e:
            print(f"获取方法范围失败 {file_path}: {e}")
            exit()
            return []

    def _find_method_body_range(self, lines, method_start_line):
        """
        查找方法体的起始和结束行

        Args:
            lines: 文件行列表
            method_start_line: 方法起始行（0-based）

        Returns:
            tuple: (start_line, end_line)，都是1-based
                   如果找不到返回(None, None)
        """
        if method_start_line >= len(lines):
            return None, None

        # 从方法定义行开始查找{
        brace_count = 0
        found_start = False

        for i in range(method_start_line, len(lines)):
            line = lines[i]

            # 计算大括号数量
            brace_count += line.count('{')
            brace_count -= line.count('}')

            if not found_start and '{' in line:
                found_start = True
                start_line = i + 1  # 转换为1-based

            if found_start and brace_count == 0:
                # 大括号匹配完成
                end_line = i + 1  # 转换为1-based
                return start_line, end_line

        # 如果方法体没有正确结束，返回文件末尾
        if found_start:
            return start_line, len(lines)

        return None, None