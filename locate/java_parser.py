#!/usr/bin/env python3
"""
Java代码解析器，使用启发式方法解析Java代码
"""

import re
import os
from pathlib import Path
import traceback


class JavaParser:
    def __init__(self):
        """
        初始化Java解析器，仅使用启发式方法
        """
        pass

    def parse_file(self, file_path):
        """
        解析Java文件

        Args:
            file_path: Java文件路径

        Returns:
            dict: 解析结果
        """
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()

            return self._parse_heuristic(content)

        except Exception as e:
            print(f"解析文件失败 {file_path}: {e}")
            return None

    
    def _parse_heuristic(self, content):
        """
        使用启发式方法解析Java文件

        Args:
            content: Java文件内容

        Returns:
            dict: 解析结果
        """
        lines = content.split('\n')

        result = {
            'methods': [],
            'classes': [],
            'imports': [],
            'fields': []
        }

        # 提取import语句
        for i, line in enumerate(lines):
            line_stripped = line.strip()
            if line_stripped.startswith('import '):
                result['imports'].append({
                    'text': line_stripped,
                    'line': i + 1
                })

        # 提取类定义
        class_pattern = re.compile(
            r'(?:public|protected|private|abstract|final|\s)*'
            r'(?:class|interface|enum|@interface)\s+'
            r'(\w+)'  # 类名
        )

        for i, line in enumerate(lines):
            match = class_pattern.search(line)
            if match:
                class_name = match.group(1)
                class_type = 'class'
                if 'interface' in line:
                    class_type = 'interface'
                elif 'enum' in line:
                    class_type = 'enum'
                elif '@interface' in line:
                    class_type = 'annotation'

                result['classes'].append({
                    'name': class_name,
                    'line': i + 1,
                    'type': class_type
                })

        # 提取方法定义（改进版本）
        # 更严格的匹配模式，避免匹配if/for/while等控制语句
        # 方法定义的正则表达式（更严格）
        # 格式: [修饰符] [泛型] 返回类型 方法名(参数) [throws 异常] {
        method_pattern = re.compile(
            r'^\s*(?:public|protected|private|static|final|synchronized|abstract|native|\s)*'
            r'(?:@\w+(?:\([^)]*\))?\s+)*'  # 注解
            r'(?:<\w+(?:,\s*\w+)*>)?\s*'  # 泛型参数
            r'(?:void|boolean|char|byte|short|int|long|float|double|[\w<>\[\],\s\.\$]+)\s+'  # 返回类型
            r'(\w+)'  # 方法名 (捕获组)
            r'\s*\([^)]*\)'  # 参数列表
            r'(?:\s*throws\s+[\w\s,\.]+)?'  # throws子句
        )

        for i, line in enumerate(lines):
            match = method_pattern.search(line)
            if match and self._is_method_definition(lines, i):
                method_name = match.group(1)

                # 提取完整的方法签名
                signature = self._extract_method_signature(lines, i)

                result['methods'].append({
                    'name': method_name,
                    'line': i + 1,
                    'signature': signature
                })

        # 提取字段定义
        field_pattern = re.compile(
            r'(?:public|protected|private|static|final|transient|volatile|\s)*'
            r'[\w<>\[\],\s]+\s+'  # 类型
            r'(\w+)'  # 字段名
        )

        for i, line in enumerate(lines):
            match = field_pattern.search(line)
            if match and self._is_field_definition(lines, i):
                result['fields'].append({
                    'name': match.group(1),
                    'line': i + 1
                })

        return result

    def _is_method_definition(self, lines, line_idx):
        """检查是否是方法定义"""
        if line_idx >= len(lines):
            return False

        line = lines[line_idx].strip()

        # 排除Java关键字开头的行（控制语句）
        java_keywords = ['if', 'for', 'while', 'switch', 'try', 'catch', 'finally',
                         'synchronized', 'return', 'throw', 'break', 'continue']

        # 检查行是否以Java关键字开头
        for keyword in java_keywords:
            if line.startswith(keyword + ' ') or line.startswith(keyword + '('):
                return False

        # 排除常见的非定义情况
        if line.endswith(';'):  # 方法调用
            return False

        if '=' in line and line.index('=') < line.find('(') and '(' in line:
            # 赋值语句中的方法调用，如: obj.method()
            return False

        # 检查访问修饰符或注解
        has_access_modifier = any(mod in line for mod in ['public ', 'protected ', 'private ', 'static '])
        has_annotation = line.strip().startswith('@')

        if not (has_access_modifier or has_annotation):
            # 没有访问修饰符或注解，可能不是方法定义
            # 但构造函数可能没有返回类型
            if line.strip().endswith('{'):  # 可能是构造函数
                # 检查是否是类名
                class_name_match = re.search(r'(\w+)\s*\([^)]*\)\s*\{', line)
                if class_name_match:
                    class_name = class_name_match.group(1)
                    # 检查这个类名是否在当前文件中定义
                    return self._is_class_name_in_file(lines, class_name)
            return False

        # 检查是否有方法体开始
        current_idx = line_idx
        brace_count = 0

        while current_idx < len(lines):
            current_line = lines[current_idx]
            brace_count += current_line.count('{')
            brace_count -= current_line.count('}')

            if brace_count > 0:
                # 找到了方法体开始
                # 进一步检查，确保不是匿名类
                if current_idx > line_idx:
                    # 检查前面几行是否有new关键字
                    for j in range(line_idx, current_idx + 1):
                        if 'new ' in lines[j] and '(' in lines[j]:
                            # 可能是匿名类
                            return False
                return True

            current_idx += 1
            if current_idx - line_idx > 10:  # 检查范围限制
                break

        return False

    def _is_class_name_in_file(self, lines, class_name):
        """检查类名是否在文件中定义"""
        class_pattern = re.compile(
            r'(?:public|protected|private|abstract|final|\s)*'
            r'(?:class|interface|enum|@interface)\s+'
            r'(\w+)'  # 类名
        )

        for line in lines:
            match = class_pattern.search(line)
            if match and match.group(1) == class_name:
                return True
        return False

    def _extract_method_signature(self, lines, start_line):
        """提取完整的方法签名"""
        signature_lines = []
        i = start_line
        max_lines = 10  # 最大查找行数

        for _ in range(max_lines):
            if i >= len(lines):
                break

            line = lines[i].strip()
            signature_lines.append(line)

            if '{' in line:
                # 找到方法体开始，停止
                signature_lines[-1] = line[:line.index('{')].strip()
                break

            i += 1

        return ' '.join(signature_lines)

    def _is_field_definition(self, lines, line_idx):
        """检查是否是字段定义"""
        if line_idx >= len(lines):
            return False

        line = lines[line_idx].strip()

        # 排除方法定义
        if '(' in line and ')' in line and line.index('(') < line.index(')'):
            # 可能有方法调用或定义
            return False

        # 字段通常以分号结束（除非有初始化）
        if ';' in line:
            return True

        # 或者有初始化但没有方法调用特征
        if '=' in line:
            # 检查等号右边是否有括号（可能是方法调用）
            equals_idx = line.index('=')
            if '(' in line[equals_idx:] and ')' in line[equals_idx:]:
                return False
            return True

        return True

    def find_function_at_line(self, file_path, line_number):
        """
        查找指定行所在的函数

        Args:
            file_path: 文件路径
            line_number: 行号（1-based）

        Returns:
            dict: 函数信息，包含name（含参数类型）, line, signature等
        """
        parse_result = self.parse_file(file_path)
        if not parse_result:
            return None

        # 查找包含指定行的方法
        target_method = None

        for method in parse_result['methods']:
            method_line = method['line']

            # 简单地假设方法体持续到下一个方法或文件末尾
            # 这是简化的实现，实际上应该解析方法体范围
            if method_line <= line_number:
                # 检查是否有更近的方法
                if not target_method or method_line > target_method['line']:
                    target_method = method

        # 如果找到了方法，提取包含参数类型的签名
        if target_method:
            # 从 signature 中提取方法名和参数类型
            signature = target_method.get('signature', '')
            method_name = target_method['name']
            
            # 提取参数类型
            param_types = self._extract_param_types_from_signature(signature, method_name)
            
            # 生成包含参数类型的方法名
            if param_types:
                full_method_name = f"{method_name}({','.join(param_types)})"
            else:
                full_method_name = f"{method_name}()"
            
            target_method = target_method.copy()
            target_method['name'] = full_method_name

        return target_method

    def _extract_param_types_from_signature(self, signature, method_name):
        """
        从方法签名中提取参数类型列表

        Args:
            signature: 方法签名字符串
            method_name: 方法名

        Returns:
            list: 参数类型列表
        """
        if not signature:
            return []
        
        # 找到方法名后面的括号
        method_name_pos = signature.find(method_name)
        if method_name_pos == -1:
            return []
        
        # 找到参数列表的起始位置
        paren_start = signature.find('(', method_name_pos)
        if paren_start == -1:
            return []
        
        # 找到参数列表的结束位置
        paren_end = signature.find(')', paren_start)
        if paren_end == -1:
            return []
        
        # 提取参数列表
        param_str = signature[paren_start + 1:paren_end].strip()
        if not param_str:
            return []
        
        # 解析参数列表，支持嵌套的泛型和数组
        param_types = []
        depth = 0
        current_param = []
        
        for char in param_str:
            if char in '(<[':
                depth += 1
                current_param.append(char)
            elif char in ')>]':
                depth -= 1
                current_param.append(char)
            elif char == ',' and depth == 0:
                # 参数分隔符
                param_type = ''.join(current_param).strip()
                if param_type:
                    # 移除参数名（如果存在），只保留类型
                    param_type = self._clean_param_type(param_type)
                    param_types.append(param_type)
                current_param = []
            else:
                current_param.append(char)
        
        # 处理最后一个参数
        if current_param:
            param_type = ''.join(current_param).strip()
            if param_type:
                param_type = self._clean_param_type(param_type)
                param_types.append(param_type)
        
        return param_types

    def _clean_param_type(self, param_str):
        """
        清理参数字符串，只保留类型部分，移除变量名和空格

        Args:
            param_str: 参数字符串，如 "String name" 或 "List<String> items"

        Returns:
            str: 只包含类型，如 "String" 或 "List<String>"
        """
        # 移除 final 修饰符
        param_str = re.sub(r'\bfinal\b', '', param_str).strip()
        
        # 参数格式可能是：
        # - "Type varName"
        # - "Type<Generic> varName"
        # - "Type[] varName"
        # - "Type<Generic>[] varName"
        # - "Type<Generic<? extends T>> varName"
        
        # 使用正则表达式匹配类型部分
        # 模式: 标识符开头，后面跟着可选的泛型<>和数组[]
        # 捕获组1会匹配到类型部分（不含变量名）
        # (?:\s+\w+)? 匹配可选的空格+变量名
        type_pattern = r'^([\w\.\$]+(?:<[^>]+>)?(?:\[ \]*)*)'
        match = re.match(type_pattern, param_str.strip())
        if match:
            param_type = match.group(1).strip()
            return param_type
        
        # 如果没有匹配到，尝试另一种方法：移除最后一个空格后的部分
        # 对于 "Class<?> expectClass" 这种情况
        if ' ' in param_str:
            parts = param_str.strip().split()
            if len(parts) >= 2:
                # 第一个部分通常是类型
                param_type = parts[0]
                return param_type
        
        # 如果没有匹配到，返回原始字符串
        return param_str.strip()

    def find_class_at_line(self, file_path, line_number):
        """查找指定行所在的类"""
        parse_result = self.parse_file(file_path)
        if not parse_result:
            return None

        target_class = None

        for cls in parse_result['classes']:
            if cls['line'] <= line_number:
                if not target_class or cls['line'] > target_class['line']:
                    target_class = cls

        return target_class

    def get_scope_at_line(self, file_path, line_number):
        """
        获取指定行的作用域信息

        Args:
            file_path: 文件路径
            line_number: 行号

        Returns:
            dict: 作用域信息，包含class, method, enclosing_methods等
        """
        parse_result = self.parse_file(file_path)
        if not parse_result:
            return None

        result = {
            'file': file_path,
            'line': line_number,
            'class': None,
            'method': None,
            'enclosing_methods': []
        }

        # 查找最近的类
        for cls in parse_result['classes']:
            if cls['line'] <= line_number:
                if not result['class'] or cls['line'] > result['class']['line']:
                    result['class'] = cls

        # 查找最近的方法
        for method in parse_result['methods']:
            if method['line'] <= line_number:
                # 这里假设方法持续到下一个方法或文件末尾
                # 实际上应该解析嵌套方法
                result['enclosing_methods'].append(method)

                if not result['method'] or method['line'] > result['method']['line']:
                    result['method'] = method

        return result

