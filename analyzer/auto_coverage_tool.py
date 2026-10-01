#!/usr/bin/env python3
"""
自动化覆盖率测试工具

该工具用于在Docker容器中运行覆盖率测试，并分析指定函数的覆盖情况。
复用了 coverage_docker.py 中的命令构建和容器操作逻辑。

支持的项目: fastjson2, dubbo, jackson-core, jackson-databind, gson, jackson-dataformat-xml

使用示例:
python auto_coverage_tool.py --image my-java-test-image --test-code "test code" \
    --target-file core/src/main/java/com/alibaba/fastjson2/JSON.java \
    --function-code "public boolean isValid()"
"""

import argparse
import json
import logging
import os
import re
import subprocess
import sys
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union
from .LogAnalyzer import TestLogAnalyzer
from .GradleLogAnalyzer import GradleLogAnalyzer

import docker
from bs4 import BeautifulSoup
import html

gradle_list = ["logstash", "jib", "mockito"]
# 初始化Docker客户端
try:
    docker_client = docker.from_env()
except Exception as e:
    logging.warning(f"Docker客户端初始化失败: {e}")
    docker_client = None


# 项目配置
PROJECT_COMMANDS = {
    "fastjson2": {
        "reprocess": """sed -i 's/<skip>false<\\/skip>/<skip>true<\\/skip>/g' pom.xml && \ 
    mkdir -p ~/.m2 && \
    if [ ! -f ~/.m2/settings.xml ]; then \
        echo '<?xml version="1.0" encoding="UTF-8"?>' > ~/.m2/settings.xml && \
        echo '<settings xmlns="http://maven.apache.org/SETTINGS/1.0.0"' >> ~/.m2/settings.xml && \
        echo '          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"' >> ~/.m2/settings.xml && \
        echo '          xsi:schemaLocation="http://maven.apache.org/SETTINGS/1.0.0 https://maven.apache.org/xsd/settings-1.0.0.xsd">' >> ~/.m2/settings.xml && \
        echo '</settings>' >> ~/.m2/settings.xml; \
    fi && \
    sed -i '$d' ~/.m2/settings.xml && \
    echo '<mirrors>' >> ~/.m2/settings.xml && \
    echo '    <mirror>' >> ~/.m2/settings.xml && \
    echo '        <id>aliyunmaven</id>' >> ~/.m2/settings.xml && \
    echo '        <name>aliyunmaven</name>' >> ~/.m2/settings.xml && \
    echo '        <url>https://maven.aliyun.com/repository/public</url>' >> ~/.m2/settings.xml && \
    echo '        <mirrorOf>central</mirrorOf>' >> ~/.m2/settings.xml && \
    echo '    </mirror>' >> ~/.m2/settings.xml && \
    echo '</mirrors>' >> ~/.m2/settings.xml && \
    echo '</settings>' >> ~/.m2/settings.xml""",
        "run": "git apply /home/fix.patch",
        "test": "./mvnw -V --no-transfer-progress -Pgen-javadoc -Pgen-dokka clean test org.jacoco:jacoco-maven-plugin:0.8.8:prepare-agent install -Dsurefire.useFile=false -Dmaven.test.skip=false -DfailIfNoTests=false -Dmaven.test.failure.ignore=true || true",
        "report": "./mvnw org.jacoco:jacoco-maven-plugin:0.8.8:report",
    },
    "dubbo": {
        "reprocess": """sed -i '$d' ~/.m2/settings.xml && \
echo '<proxies>' >> ~/.m2/settings.xml && \
echo '    <proxy>' >> ~/.m2/settings.xml && \
echo '        <id>example-proxy</id>' >> ~/.m2/settings.xml && \
echo '        <active>true</active>' >> ~/.m2/settings.xml && \
echo '        <protocol>http</protocol>' >> ~/.m2/settings.xml && \
echo '        <host>172.19.135.130</host>' >> ~/.m2/settings.xml && \
echo '        <port>5000</port>' >> ~/.m2/settings.xml && \
echo '        <username></username>' >> ~/.m2/settings.xml && \
echo '        <password></password>' >> ~/.m2/settings.xml && \
echo '        <nonProxyHosts></nonProxyHosts>' >> ~/.m2/settings.xml && \
echo '    </proxy>' >> ~/.m2/settings.xml && \
echo '</proxies>' >> ~/.m2/settings.xml && \
echo '<mirrors>' >> ~/.m2/settings.xml && \
echo '    <mirror>' >> ~/.m2/settings.xml && \
echo '        <id>aliyunmaven</id>' >> ~/.m2/settings.xml && \
echo '        <name>阿里云公共仓库</name>' >> ~/.m2/settings.xml && \
echo '        <url>https://maven.aliyun.com/repository/public</url>' >> ~/.m2/settings.xml && \
echo '        <mirrorOf>central</mirrorOf>' >> ~/.m2/settings.xml && \
echo '    </mirror>' >> ~/.m2/settings.xml && \
echo '</mirrors>' >> ~/.m2/settings.xml && \
echo '</settings>' >> ~/.m2/settings.xml""",
        "run": "git apply --whitespace=nowarn /home/fix.patch",
        "test": "mvn clean test org.jacoco:jacoco-maven-plugin:0.8.8:prepare-agent install -Dsurefire.useFile=false -Dmaven.test.skip=false -DfailIfNoTests=false -Dstyle.color=never -Dmaven.test.failure.ignore=true || true",
        "report": "mvn org.jacoco:jacoco-maven-plugin:0.8.8:report",
    },
    "jackson-core": {
        "reprocess": "",
        "run": "git apply --whitespace=nowarn /home/fix.patch",
        "test": "mvn clean test -Dmaven.test.skip=false -DfailIfNoTests=false -Dstyle.color=never org.jacoco:jacoco-maven-plugin:0.8.8:prepare-agent install -Dmaven.test.failure.ignore=true || true",
        "report": "mvn org.jacoco:jacoco-maven-plugin:0.8.8:report",
    },
    "jackson-databind": {
        "reprocess": """sed -i '$d' ~/.m2/settings.xml && \
echo '<mirrors>' >> ~/.m2/settings.xml && \
echo '    <mirror>' >> ~/.m2/settings.xml && \
echo '        <id>aliyunmaven</id>' >> ~/.m2/settings.xml && \
echo '        <name>阿里云公共仓库</name>' >> ~/.m2/settings.xml && \
echo '        <url>https://maven.aliyun.com/repository/public</url>' >> ~/.m2/settings.xml && \
echo '        <mirrorOf>central</mirrorOf>' >> ~/.m2/settings.xml && \
echo '    </mirror>' >> ~/.m2/settings.xml && \
echo '</mirrors>' >> ~/.m2/settings.xml && \
echo '</settings>' >> ~/.m2/settings.xml""",
        "run": "git apply --whitespace=nowarn /home/fix.patch",
        "test": "mvn clean test -Dmaven.test.skip=false -DfailIfNoTests=false -Dstyle.color=never org.jacoco:jacoco-maven-plugin:0.8.8:prepare-agent install -Dmaven.test.failure.ignore=true || true",
        "report": "mvn org.jacoco:jacoco-maven-plugin:0.8.8:report",
    },
    "gson": {
        "reprocess": """sed -i '$d' ~/.m2/settings.xml && \
echo '<mirrors>' >> ~/.m2/settings.xml && \
echo '    <mirror>' >> ~/.m2/settings.xml && \
echo '        <id>aliyunmaven</id>' >> ~/.m2/settings.xml && \
echo '        <name>阿里云公共仓库</name>' >> ~/.m2/settings.xml && \
echo '        <url>https://maven.aliyun.com/repository/public</url>' >> ~/.m2/settings.xml && \
echo '        <mirrorOf>central</mirrorOf>' >> ~/.m2/settings.xml && \
echo '    </mirror>' >> ~/.m2/settings.xml && \
echo '</mirrors>' >> ~/.m2/settings.xml && \
echo '</settings>' >> ~/.m2/settings.xml""",
        "run": "git apply --whitespace=nowarn /home/fix.patch",
        "test": "mvn clean test -Dmaven.test.skip=false -DfailIfNoTests=false -Dstyle.color=never org.jacoco:jacoco-maven-plugin:0.8.8:prepare-agent install -Dmaven.test.failure.ignore=true || true",
        "report": "mvn org.jacoco:jacoco-maven-plugin:0.8.8:report",
    },
    "jackson-dataformat-xml": {
        "reprocess": """sed -i '$d' ~/.m2/settings.xml && \
echo '<mirrors>' >> ~/.m2/settings.xml && \
echo '    <mirror>' >> ~/.m2/settings.xml && \
echo '        <id>aliyunmaven</id>' >> ~/.m2/settings.xml && \
echo '        <name>阿里云公共仓库</name>' >> ~/.m2/settings.xml && \
echo '        <url>https://maven.aliyun.com/repository/public</url>' >> ~/.m2/settings.xml && \
echo '        <mirrorOf>central</mirrorOf>' >> ~/.m2/settings.xml && \
echo '    </mirror>' >> ~/.m2/settings.xml && \
echo '</mirrors>' >> ~/.m2/settings.xml && \
echo '</settings>' >> ~/.m2/settings.xml""",
        "run": "git apply --whitespace=nowarn /home/fix.patch",
        "test": "mvn clean test -Dmaven.test.skip=false -DfailIfNoTests=false -Dstyle.color=never org.jacoco:jacoco-maven-plugin:0.8.8:prepare-agent install -Dmaven.test.failure.ignore=true || true",
        "report": "mvn org.jacoco:jacoco-maven-plugin:0.8.8:report",
    },
    "nacos": {
        "reprocess": "sed -i 's/<includeTestSourceDirectory>true<\/includeTestSourceDirectory>/<includeTestSourceDirectory>false<\/includeTestSourceDirectory>/g' pom.xml",
        "run": "git apply /home/fix.patch",
        "test": "./mvnw clean test -Dsurefire.useFile=false -Dmaven.test.skip=false -DfailIfNoTests=false -Dmaven.test.failure.ignore=true --fail-at-end || true",
        "report": "./mvnw org.jacoco:jacoco-maven-plugin:0.8.13:report",
    },
    "guava": {
        "reprocess": "sed -i '/<argLine>.*<\\/argLine>/s/.*/<!-- & -->/' pom.xml",
        "run": "git apply /home/fix.patch",
        "test": "./mvnw test -Dmaven.test.skip=false -DfailIfNoTests=false org.jacoco:jacoco-maven-plugin:0.8.12:prepare-agent install --fail-at-end -DargLine=\"-Xmx1536M -Duser.language=hi -Duser.country=IN --add-opens java.base/java.lang=ALL-UNNAMED --add-opens java.base/java.util=ALL-UNNAMED --add-opens java.base/sun.security.jca=ALL-UNNAMED -javaagent:/root/.m2/repository/org/jacoco/org.jacoco.agent/0.8.12/org.jacoco.agent-0.8.12-runtime.jar=destfile=target/jacoco.exec,output=file\" || true",
        "report": "./mvnw org.jacoco:jacoco-maven-plugin:0.8.12:report-aggregate",
    }
}


@dataclass
class CoverageResult:
    """覆盖率结果数据类"""
    instruction_coverage: float = 0.0
    branch_coverage: float = 0.0
    line_coverage: float = 0.0
    total_lines_num: int = 0
    missed_lines_num: int = 0
    total_branches: int = 0
    missed_branches: int = 0


@dataclass
class FunctionCoverageReport:
    """函数覆盖率报告"""
    function_name: str = ""
    function_signature: str = ""
    file_path: str = ""
    start_line: int = 0  # 函数在文件中的起始行号
    end_line: int = 0
    coverage: CoverageResult = field(default_factory=CoverageResult)
    covered_lines: List[int] = field(default_factory=list)
    missed_lines: List[int] = field(default_factory=list)
    covered_branches: List[Tuple[int, str]] = field(default_factory=list)
    missed_branches: List[Tuple[int, str]] = field(default_factory=list)
    source_code: str = ""


@dataclass
class CoverageTestConfig:
    """覆盖率测试配置"""
    image_name: str
    test_code: str
    test_file_path: str
    method_name: str
    function_code: str
    project_name: str = "fastjson2"  # 项目名称，用于选择对应的命令集
    project_dir: str = "/home/project"
    output_dir: str = "./coverage_output"


def get_project_commands(project_name: str) -> Dict[str, str]:
    """获取指定项目的命令集"""
    for key in PROJECT_COMMANDS:
        if key in project_name.lower():
            return PROJECT_COMMANDS[key]
    # 默认返回fastjson2的命令
    return PROJECT_COMMANDS["fastjson2"]


def copy_coverage_reports(container_name: str, project_path: Path, output_path: Path, module_name: str):
    """
    从项目目录复制覆盖率报告到输出目录

    Args:
        container_name: 容器名称
        project_path: 项目目录路径
        output_path: 输出目录路径
        module_name: 模块名称
    """
    if module_name == "guava-gwt":
        jacoco_dir = project_path / module_name / "target" / "site" / "jacoco-aggregate"
    else:
        jacoco_dir = project_path / module_name / "target" / "site" / "jacoco"
    src = f"{container_name}:{jacoco_dir}"

    result = subprocess.run(['docker', 'cp', src, output_path], capture_output=True, text=True)
    if result.returncode != 0:
        logging.error(f"复制覆盖率报告失败: {result.stderr}")
    else:
        logging.info(f"覆盖率报告已复制到: {output_path}")


class CoverageReportParser:
    """JaCoCo覆盖率报告解析器"""

    def __init__(self, html_file: str):
        self.html_file = html_file
        self.soup = None
        self.coverage_data: Dict[str, Dict] = {}

    def parse(self) -> bool:
        """解析HTML文件"""
        if not os.path.exists(self.html_file):
            logging.error(f"文件不存在: {self.html_file}")
            return False

        try:
            with open(self.html_file, 'r', encoding='utf-8') as f:
                html_content = f.read()

            self.soup = BeautifulSoup(html_content, 'html.parser')
            return self._extract_coverage_data()
        except Exception as e:
            logging.error(f"解析HTML失败: {e}")
            return False

    def _extract_coverage_data(self) -> bool:
        """提取覆盖率数据"""
        table = self.soup.find('table', {'class': 'coverage'})
        if not table:
            logging.warning("未找到覆盖率表格")
            return False

        tbody = table.find('tbody')
        if not tbody:
            logging.warning("未找到表格主体")
            return False

        rows = tbody.find_all('tr')
        for row in rows:
            method_td = row.find('td', {'id': True})
            if not method_td:
                continue

            method_link = method_td.find('a', {'class': 'el_method'})
            if not method_link:
                continue

            method_name = method_link.text.strip()
            cells = row.find_all('td')

            try:
                instr_coverage = self._parse_percentage(cells[2].text.strip())
                branch_coverage = self._parse_percentage(cells[4].text.strip())
                total_lines = int(cells[8].text.strip()) if cells[8].text.strip().isdigit() else 0
                missed_lines = int(cells[7].text.strip()) if cells[7].text.strip().isdigit() else 0

                line_coverage = 0
                if total_lines > 0:
                    line_coverage = round((total_lines - missed_lines) / total_lines * 100, 2)

                self.coverage_data[method_name] = {
                    'instruction_coverage': instr_coverage,
                    'branch_coverage': branch_coverage,
                    'line_coverage': line_coverage,
                    'total_lines': total_lines,
                    'missed_lines': missed_lines
                }
            except (ValueError, IndexError) as e:
                logging.warning(f"解析方法 {method_name} 时出错: {e}")
                continue

        return True

    def _parse_percentage(self, text: str) -> float:
        """解析百分比"""
        if text == 'n/a':
            return 0.0
        if text.endswith('%'):
            text = text.rstrip('%')
        try:
            return float(text)
        except ValueError:
            return 0.0

    def get_function_coverage(self, function_name: str) -> Optional[Dict]:
        """获取函数覆盖率"""
        if not self.coverage_data:
            return None

        # 精确匹配
        if function_name in self.coverage_data:
            return {function_name: self.coverage_data[function_name]}

        # 前缀匹配
        for name, data in self.coverage_data.items():
            if name.startswith(function_name):
                return {name: data}

        return None


class JacocoHtmlAnalyzer:
    """JaCoCo HTML分析器"""

    def __init__(self, jacoco_dir: str):
        self.jacoco_dir = Path(jacoco_dir).resolve()
        if not self.jacoco_dir.exists():
            raise FileNotFoundError(f"JaCoCo目录不存在: {self.jacoco_dir}")

    def find_html_file(self, file_path: str) -> Optional[Path]:
        """查找对应的HTML文件"""
        file_path = file_path.replace("\\", "/")
        file_name = Path(file_path).name
        html_name = file_name.replace('.java', '.html')
        sub_dir_name = file_path[file_path.find('/com/')+1:file_path.rfind('/')].replace('/', '.')
        sub_jacoco_dir = self.jacoco_dir / sub_dir_name

        if not sub_jacoco_dir.exists():
            logging.error(f"子目录不存在: {sub_jacoco_dir}")
            return None

        html_files = list(sub_jacoco_dir.rglob("*.html"))

        for html_file in html_files:
            if html_file.name == html_name:
                return html_file

        return None

    def find_source_html_file(self, file_path: str) -> Optional[Path]:
        """查找源码HTML文件（包含行覆盖详情）"""
        file_path = file_path.replace("\\", "/")
        file_name = Path(file_path).name
        html_name = file_name + '.html'
        sub_dir_name = file_path[file_path.find('/com/')+1:file_path.rfind('/')].replace('/', '.')
        sub_jacoco_dir = self.jacoco_dir / sub_dir_name

        if not sub_jacoco_dir.exists():
            logging.error(f"子目录不存在: {sub_jacoco_dir}")
            return None

        html_files = list(sub_jacoco_dir.rglob("*.html"))

        for html_file in html_files:
            if html_file.name == html_name:
                return html_file

        return None

    def analyze_function(self, file_path: str, function_name: str) -> Optional[Dict]:
        """分析函数覆盖率"""
        html_file = self.find_html_file(file_path)
        if not html_file:
            logging.error(f"找不到HTML报告文件: {file_path}")
            return None

        parser = CoverageReportParser(str(html_file))
        if not parser.parse():
            return None

        return parser.get_function_coverage(function_name)


class SourceCodeCoverageAnalyzer:
    """源码覆盖率分析器 - 解析.java.html文件获取行级覆盖详情"""

    def __init__(self, source_html_file: str):
        self.source_html_file = source_html_file
        self.soup = None

    def parse(self) -> bool:
        """解析源码HTML文件"""
        if not os.path.exists(self.source_html_file):
            logging.error(f"源码HTML文件不存在: {self.source_html_file}")
            return False

        try:
            with open(self.source_html_file, 'r', encoding='utf-8') as f:
                html_content = f.read()
            self.soup = BeautifulSoup(html_content, 'html.parser')
            return True
        except Exception as e:
            logging.error(f"解析源码HTML失败: {e}")
            return False

    def extract_line_coverage(self, function_lines: List[Tuple[int, str]]) -> FunctionCoverageReport:
        """
        从源码HTML中提取函数的行覆盖信息

        通过代码内容匹配在HTML文件中找到函数的位置，然后收集该函数
        范围内所有可执行代码行的覆盖情况。

        Args:
            function_lines: 函数代码行列表 (相对行号, 代码)

        Returns:
            函数覆盖报告，行号使用相对行号（从1开始）
        """
        report = FunctionCoverageReport()

        if not self.soup or not function_lines:
            return report

        # 1. 获取HTML中所有代码行（包括不在span中的）
        pre_elem = self.soup.find('pre', {'class': 'source'})
        if not pre_elem:
            return report

        # 获取<pre>内的纯文本，按行分割
        all_text = pre_elem.get_text()
        file_lines = all_text.split('\n')  # 索引0对应第1行

        # 2. 准备函数代码用于匹配（提取非空行，去除前导空格）
        func_code_lines = []
        for rel_line, code in function_lines:
            stripped = code.strip()
            if stripped:
                func_code_lines.append((rel_line, stripped))

        if not func_code_lines:
            return report

        # 3. 在文件代码行中查找函数位置
        # 使用函数代码中的非空行进行匹配
        start_abs_line = None
        match_len = len(func_code_lines)

        for file_idx in range(len(file_lines)):
            file_line_stripped = file_lines[file_idx].strip()
            if not file_line_stripped:
                continue

            # 尝试匹配函数代码的第一行非空行
            if file_line_stripped != func_code_lines[0][1]:
                continue

            # 验证后续行是否匹配
            matched_count = 1
            file_scan_idx = file_idx + 1
            func_scan_idx = 1

            while func_scan_idx < match_len and file_scan_idx < len(file_lines):
                file_scan_stripped = file_lines[file_scan_idx].strip()
                if not file_scan_stripped:
                    file_scan_idx += 1
                    continue

                file_scan_stripped = html.unescape(file_scan_stripped)
                if file_scan_stripped != func_code_lines[func_scan_idx][1]:
                    break

                matched_count += 1
                file_scan_idx += 1
                func_scan_idx += 1

            # 要求匹配所有行
            if matched_count == match_len:
                start_abs_line = file_idx + 1  # 文件行号从1开始
                break

        if start_abs_line is None:
            return report

        # 4. 计算函数的绝对行号范围
        func_total_lines = len(function_lines)
        end_abs_line = start_abs_line + func_total_lines - 1

        # 5. 收集span的覆盖信息映射: 绝对行号 -> (class_str, relative_line)
        line_spans = self.soup.find_all('span', id=True)
        span_map = {}  # 绝对行号 -> span元素

        for span in line_spans:
            span_id = span.get('id', '')
            if not span_id.startswith('L'):
                continue
            try:
                abs_line = int(span_id[1:])
            except ValueError:
                continue
            span_map[abs_line] = span

        # 6. 收集函数范围内的覆盖情况
        covered_lines = set()
        missed_lines = set()

        for abs_line in range(start_abs_line, end_abs_line + 1):
            if abs_line not in span_map:
                continue

            span = span_map[abs_line]
            span_class = span.get('class', [])
            class_str = ' '.join(span_class) if isinstance(span_class, list) else str(span_class)

            relative_line = abs_line - start_abs_line + 1

            if 'nc' in class_str:
                missed_lines.add(relative_line)
            elif 'fc' in class_str or 'pc' in class_str:
                covered_lines.add(relative_line)
            # pc (部分覆盖) 不计入

        report.start_line = start_abs_line
        report.end_line = end_abs_line
        report.covered_lines = sorted(list(covered_lines))
        report.missed_lines = sorted(list(missed_lines))

        total_lines = len(covered_lines) + len(missed_lines)
        if total_lines > 0:
            report.coverage.line_coverage = round(len(covered_lines) / total_lines * 100, 2)
            report.coverage.total_lines_num = total_lines
            report.coverage.missed_lines_num = len(missed_lines)

        return report


class CoverageTestRunner:
    """覆盖率测试运行器"""

    def __init__(self, config: CoverageTestConfig):
        self.config = config
        self.container = None
        self.jacoco_dir = ""

    def run(self) -> bool:
        """
        运行覆盖率测试

        Returns:
            是否成功
        """
        # jacoco_dir = f"{self.config.output_dir}/jacoco"
        # if os.path.exists(jacoco_dir):
        #     print("覆盖率已经收集完毕，跳过测试")
        #     self.jacoco_dir = jacoco_dir
        #     return True

        try:
            # 确保输出目录存在
            output_path = Path(self.config.output_dir)
            output_path.mkdir(parents=True, exist_ok=True)

            # 获取项目命令
            commands = get_project_commands(self.config.project_name)

            # 构建测试命令
            command = self._build_test_command(commands)

            print(f"启动容器: {self.config.image_name}")
            print(f"项目: {self.config.project_name}")
            print(f"目标文件: {self.config.test_file_path}")

            # 启动容器
            self.container = docker_client.containers.run(
                image=self.config.image_name,
                command=["bash", "-c", command],
                remove=False,
                detach=True,
                stdout=True,
                stderr=True,
            )

            output = ""
            output_file = output_path / "run.log"

            # 实时读取和保存输出
            with open(output_file, "w", encoding="utf-8") as f:
                for line in self.container.logs(stream=True, follow=True):
                    line_decoded = line.decode("utf-8")
                    f.write(line_decoded)
                    output += line_decoded
                    # print(line_decoded, end="")

            # 等待容器执行完成
            self.container.wait()

            # 获取模块名
            method_name = self.config.method_name
            module_name = method_name.split('/')[0] if 'src' != method_name.split('/')[0] else ""
            if module_name == 'guava':
                module_name = 'guava-gwt'

            # 复制覆盖率报告
            project_path = Path(self.config.project_dir).resolve()
            dest_path = os.path.join(os.path.abspath(self.config.output_dir), "jacoco")
            copy_coverage_reports(self.container.name, project_path, output_path, module_name)

            self.jacoco_dir = dest_path
            print(f"覆盖率报告已保存到: {dest_path}")

            return True

        except Exception as e:
            logging.error(f"运行覆盖率测试失败: {e}")
            return False
        finally:
            self._cleanup_container()

    def _build_test_command(self, commands: Dict[str, str]) -> str:
        """构建测试命令"""
        # 写入测试代码
        escaped_code = json.dumps(self.config.test_code)
        target_path = self.config.test_file_path
        file_dir = os.path.dirname(target_path)
        file_name = os.path.basename(target_path)

        reprocess = commands.get("reprocess", "")
        run_cmd = commands.get("run", "")
        test_cmd = commands.get("test", "")
        report_cmd = commands.get("report", "")

        insert_command = f"""cd {file_dir}
echo -e {escaped_code} > {file_name}
"""

        if reprocess:
            combined = f"""{insert_command}
cd {self.config.project_dir}
{reprocess} && {run_cmd} && {test_cmd} && {report_cmd}
"""
        else:
            combined = f"""{insert_command}
cd {self.config.project_dir}
{run_cmd} && {test_cmd} && {report_cmd}
"""

        return combined

    def _cleanup_container(self):
        """清理容器"""
        if self.container:
            try:
                self.container.stop(timeout=100)
            except Exception:
                pass
            try:
                self.container.remove(force=True)
            except Exception as e:
                logging.warning(f"删除容器失败: {e}")


def parse_failures_from_log(log_path: str) -> str:
    """
    从 fix-patch-run 日志中提取 Failures 和 Errors 的报错信息字符串。
    返回所有报错行的原始文本，每行以换行符分隔。
    如果没有报错，返回空字符串。
    """
    with open(log_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    results_line_idx = -1
    for idx, line in enumerate(lines):
        if '[INFO] Results:' in line:
            results_line_idx = idx
            break
    
    if results_line_idx == -1:
        print("[警告] 未找到 '[INFO] Results:' 行，无法按 Results 之后提取错误。", file=sys.stderr)
        return ""
    
    # 2. 从 Results 下一行开始扫描，收集错误行，直到遇到汇总行
    errors_raw = []
    for line in lines[results_line_idx + 1:]:
        stripped = line.strip()
        # 停止条件：遇到 '[ERROR] Tests run:' 开头的行
        if stripped.startswith('[ERROR] Tests run:'):
            break
        # 收集其他以 [ERROR] 开头的行
        if stripped.startswith('[ERROR]'):
            errors_raw.append(stripped)
            
    return "\n".join(errors_raw)

def analyze_run_log(analyzer, run_log_path: str, test_file_path: str) -> Dict:
    """
    只分析 fix-patch-run 开头的日志文件，统计每个文件对应测试类的测试用例信息。
    返回字典，键为日志文件相对路径（相对于 run_log_dir），值为：
    {
        'total': int,           # 该测试类的总用例数
        'passed': int,          # 通过用例数
        'failed': int,          # 失败用例数
        'failures_detail': str,  # 仅当 failed>0 时存在，包含失败详细信息
        'test_class': str,      # 测试类名（简单类名）
        'pr_number': str        # 从父目录名提取的 PR 号
    }
    """
    run_log = Path(run_log_path)

    test_class_name = Path(test_file_path).stem

    stats = analyzer.get_test_class_stats(str(run_log), test_class_name)
    
    if stats is None:
        print(f"⚠️ 执行日志中未找到测试类")
        entry = {
            'total': 0,
            'passed': 0,
            'failed': 0,
            'test_class': test_class_name,
            'failures_detail': "This test class has not been executed."
        }
        return entry
            

    total = stats.get('total', 0)
    passed = stats.get('passed', 0)
    failed = stats.get('failed', 0)

    # 4. 构建结果条目
    entry = {
        'total': total,
        'passed': passed,
        'failed': failed,
        'test_class': test_class_name,
    }

    # 5. 若失败数 > 0，提取失败详情
    if failed > 0:
        failures_detail = parse_failures_from_log(str(run_log))
        entry['failures_detail'] = failures_detail
        # 打印到控制台以便查看（可选）
        print(f"\n🔍 发现失败用例 ({failed}/{total}) 在 {test_class_name}")

    else:
        print(f"✅ {test_class_name}: 全部通过 ({passed}/{total})")

    print(f"\n📊 {test_class_name} 用例数 {total}, 通过 {passed}, 失败 {failed}")
    
    return entry

def extract_function_name(function_code: str) -> str:
    """从函数代码提取函数名（包含参数类型）
    
    例如: public boolean parseObject(String input, Type type) -> parseObject(String, Type)
    """
    lines = function_code.strip().split('\n')
    
    # 找到包含函数签名的那一行（包含括号，且去除注解后不为空）
    signature_line = None
    for line in lines:
        stripped = line.strip()
        # 去除注解
        clean = re.sub(r'@\w+(?:\([^)]*\))?\s*', '', stripped).strip()
        # 如果去除注解后为空（只有注解），跳过这一行
        if not clean:
            continue
        # 如果这一行包含括号，这就是函数签名行
        if '(' in clean:
            signature_line = clean
            break
    
    if not signature_line:
        return lines[0].strip() if lines else ""
    
    # 匹配函数名（支持public/private/protected/static修饰符）
    func_match = re.search(
        r'(?:(?:public|private|protected)\s+)?(?:static\s+)?[\w<>[\],\s]+\s+(\w+)\s*\(',
        signature_line
    )
    if not func_match:
        # 尝试更简单的匹配
        func_match = re.search(r'(\w+)\s*\(', signature_line)
        if not func_match:
            return signature_line.strip()
    
    func_name = func_match.group(1)
    start_pos = func_match.end() - 1  # 回到 '(' 的位置
    
    if start_pos >= len(signature_line) or signature_line[start_pos] != '(':
        return func_name
    
    # 使用栈来追踪括号匹配，处理嵌套括号如泛型<Map<String, List<Integer>>>
    stack = ['(']
    i = start_pos + 1
    
    while i < len(signature_line) and stack:
        if signature_line[i] == '(':
            stack.append('(')
        elif signature_line[i] == ')':
            stack.pop()
        i += 1
    
    param_str = signature_line[start_pos:i]
    
    # 提取参数部分，去除参数名只保留类型
    return extract_param_types(func_name, param_str)


def extract_param_types(func_name: str, param_str: str) -> str:
    """从参数字符串提取参数类型列表
    
    例如: (String input, Type type) -> (String, Type)
    """
    if not param_str or param_str == '()':
        return f"{func_name}()"
    
    # 去掉首尾括号
    inner = param_str[1:-1].strip()
    if not inner:
        return f"{func_name}()"
    
    result_types = []
    current_type = []
    bracket_depth = 0
    angle_bracket_depth = 0
    
    i = 0
    while i < len(inner):
        c = inner[i]
        
        if c == '<':
            angle_bracket_depth += 1
            current_type.append(c)
        elif c == '>':
            angle_bracket_depth -= 1
            current_type.append(c)
        elif c == '(':
            bracket_depth += 1
            current_type.append(c)
        elif c == ')':
            bracket_depth -= 1
            current_type.append(c)
        elif c == '[':
            # 遇到数组括号，将类型和[]一起加入
            current_type.append(c)
        elif c == ']' and angle_bracket_depth == 0 and bracket_depth == 0:
            # 数组结束
            current_type.append(c)
        elif c == ',' and angle_bracket_depth == 0 and bracket_depth == 0:
            # 参数字符串分隔符
            type_str = ''.join(current_type).strip()
            if type_str:
                # 移除参数名，只保留类型（取最后一个单词作为类型）
                # 处理复杂类型如 Map<String, Object>、String[] 等
                result_types.append(extract_type_from_param(type_str))
            current_type = []
        else:
            current_type.append(c)
        
        i += 1
    
    # 处理最后一个参数
    if current_type:
        type_str = ''.join(current_type).strip()
        if type_str:
            result_types.append(extract_type_from_param(type_str))
    
    return f"{func_name}({', '.join(result_types)})"


def extract_type_from_param(type_str: str) -> str:
    """从参数声明中提取类型（去除变量名）
    
    例如: "String input" -> "String"
          "Map<String, Object> map" -> "Map<String, Object>"
          "Filter[] filters" -> "Filter[]"
          "final String name" -> "String"
    """
    type_str = type_str.strip()
    if not type_str:
        return type_str
    
    # 去除常见的修饰符
    modifiers = ['final', 'transient', 'volatile', '@Nullable', '@NotNull', '@NonNull']
    for mod in modifiers:
        if type_str.startswith(mod + ' '):
            type_str = type_str[len(mod):].strip()
    
    # 如果包含泛型，需要找到完整的泛型类型
    if '<' in type_str:
        # 找到类型名开始位置
        angle_start = type_str.find('<')
        # 找到匹配的 > 
        depth = 0
        angle_end = -1
        for i in range(angle_start, len(type_str)):
            if type_str[i] == '<':
                depth += 1
            elif type_str[i] == '>':
                depth -= 1
                if depth == 0:
                    angle_end = i
                    break
        
        if angle_end > 0:
            # 类型名 + 泛型参数
            type_name = type_str[:angle_start].strip().split()[-1]
            return type_name + type_str[angle_start:angle_end+1]
    
    # 如果包含数组
    if '[]' in type_str:
        # 找到数组括号的位置
        bracket_pos = type_str.find('[')
        type_part = type_str[:bracket_pos].strip()
        # 类型名是最后一个词（在数组括号前）
        type_name = type_part.split()[-1]
        # 计算数组维度
        array_suffix = ''
        i = bracket_pos
        while i < len(type_str) and type_str[i:i+2] == '[]':
            array_suffix += '[]'
            i += 2
        return type_name + array_suffix
    
    # 简单类型，取第一个词（类型名）
    parts = type_str.split()
    return parts[0] if parts else type_str


def parse_function_code(function_code: str) -> List[Tuple[int, str]]:
    """解析函数代码，返回行号和代码行的列表"""
    lines = function_code.strip().split('\n')
    result = []
    for i, line in enumerate(lines, 1):
        result.append((i, line))
    return result


def generate_coverage_report(
    jacoco_dir: str,
    target_file: str,
    function_code: str,
    output_file: Optional[str] = None
) -> FunctionCoverageReport:
    """
    生成覆盖率报告

    Args:
        jacoco_dir: JaCoCo报告目录
        target_file: 目标文件路径
        function_code: 函数代码
        output_file: 输出文件路径

    Returns:
        函数覆盖率报告
    """
    analyzer = JacocoHtmlAnalyzer(jacoco_dir)

    function_name = extract_function_name(function_code)

    print(f"分析函数: {function_name}")
    print(f"目标文件: {target_file}")

    # 获取函数覆盖率
    coverage_info = analyzer.analyze_function(target_file, function_name)

    # 获取源码覆盖详情
    source_html = analyzer.find_source_html_file(target_file)

    report = FunctionCoverageReport()
    report.function_name = function_name
    report.function_signature = function_code
    report.file_path = target_file

    if coverage_info:
        for name, data in coverage_info.items():
            report.coverage.instruction_coverage = data.get('instruction_coverage', 0)
            report.coverage.branch_coverage = data.get('branch_coverage', 0)
            report.coverage.line_coverage = data.get('line_coverage', 0)
            report.coverage.total_lines_num = data.get('total_lines', 0)
            report.coverage.missed_lines_num = data.get('missed_lines', 0)

    if source_html:
        source_analyzer = SourceCodeCoverageAnalyzer(str(source_html))
        if source_analyzer.parse():
            function_lines = parse_function_code(function_code)
            line_report = source_analyzer.extract_line_coverage(function_lines)
            report.covered_lines = line_report.covered_lines
            report.missed_lines = line_report.missed_lines
            report.start_line = line_report.start_line
            report.end_line = line_report.end_line

    # 保存报告
    if output_file:
        save_report(report, output_file)

    return report


def save_report(report: FunctionCoverageReport, output_file: str):
    """保存报告到文件"""
    with open(output_file, 'a', encoding='utf-8') as f:
        f.write("=" * 60 + "\n")
        f.write("函数覆盖率详细报告\n")
        f.write("=" * 60 + "\n\n")

        f.write(f"函数名: {report.function_name}\n")
        f.write(f"文件路径: {report.file_path}\n")
        f.write(f"起始行号: {report.start_line}\n\n")

        f.write("覆盖率指标:\n")
        f.write("-" * 40 + "\n")
        f.write(f"  指令覆盖率: {report.coverage.instruction_coverage}%\n")
        f.write(f"  分支覆盖率: {report.coverage.branch_coverage}%\n")
        f.write(f"  行覆盖率: {report.coverage.line_coverage}%\n")
        f.write(f"  总行数: {report.coverage.total_lines_num}\n")
        f.write(f"  未覆盖行数: {report.coverage.missed_lines_num}\n\n")

        if report.covered_lines:
            f.write(f"已覆盖行 ({len(report.covered_lines)}行):\n")
            f.write(f"  {report.covered_lines}\n\n")

        if report.missed_lines:
            f.write(f"未覆盖行 ({len(report.missed_lines)}行):\n")
            f.write(f"  {report.missed_lines}\n\n")

        f.write("=" * 60 + "\n")


def save_test_result_to_report(entry: Dict, output_file: str):
    """
    将测试执行结果追加写入报告文件

    Args:
        entry: analyze_run_log 返回的结果字典
        output_file: 报告文件路径
    """
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("\n" + "=" * 60 + "\n")
        f.write("测试执行结果\n")
        f.write("=" * 60 + "\n\n")
        f.write(f"测试类: {entry.get('test_class', 'N/A')}\n")
        f.write(f"总用例数: {entry.get('total', 0)}\n")
        f.write(f"通过: {entry.get('passed', 0)}\n")
        f.write(f"失败: {entry.get('failed', 0)}\n")
        if 'failures_detail' in entry:
            f.write(f"\n失败详情:\n{entry['failures_detail']}\n")


def _annotate_uncovered_lines(function_code: str, uncovered_lines: List[int]) -> str:
    """
    在函数代码的未覆盖行后添加//UNCOVERED注释

    Args:
        function_code: 函数代码
        uncovered_lines: 未覆盖的行号列表

    Returns:
        带//UNCOVERED注释的函数代码
    """
    if not function_code:
        return ""

    uncovered_set = set(uncovered_lines)
    lines = function_code.split('\n')
    annotated_lines = []

    for i, line in enumerate(lines, 1):
        annotated_lines.append(line)
        if i in uncovered_set:
            # 检查行末尾的空白，添加注释
            stripped = line.rstrip()
            if stripped.endswith('//UNCOVERED'):
                continue  # 已经添加过
            spaces = len(line) - len(line.rstrip())
            indent = ' ' * spaces
            annotated_lines[-1] = f"{indent}{stripped}  //UNCOVERED"

    return '\n'.join(annotated_lines)




def format_coverage_report(coverage_info: Dict) -> str:
    """
    格式化覆盖率信息为可读字符串

    Args:
        coverage_info: get_function_coverage_info 返回的字典

    Returns:
        格式化的报告字符串
    """
    if not coverage_info["success"]:
        return f"获取覆盖率信息失败: {coverage_info['error']}"

    lines = []
    lines.append("=" * 60)
    lines.append("函数覆盖率详细报告")
    lines.append("=" * 60)
    lines.append(f"函数名: {coverage_info['function_name']}")
    lines.append(f"文件路径: {coverage_info['file_path']}")
    lines.append("")
    lines.append("覆盖率指标:")
    lines.append("-" * 40)
    lines.append(f"  instruction_coverage: {coverage_info['instruction_coverage']}%")
    lines.append(f"  分支覆盖率: {coverage_info['branch_coverage']}%")
    lines.append(f"  行覆盖率: {coverage_info['line_coverage']}%")
    lines.append(f"  总行数: {coverage_info['total_lines_num']}")
    lines.append(f"  未覆盖行数: {coverage_info['missed_lines_num']}")
    lines.append("")

    # 显示带注释的代码
    if coverage_info.get('annotated_code'):
        lines.append("函数代码（未覆盖行已标记）:")
        lines.append("-" * 40)
        lines.append(coverage_info['annotated_code'])
        lines.append("")

    lines.append("=" * 60)
    return "\n".join(lines)

def run_coverage_analysis(json_file: str, project_name: str, max_workers: int = 4, skip_test: bool = False) -> Dict:
    """
    多线程并行执行覆盖率分析
    
    Args:
        json_file: JSON配置文件路径
        project_name: 项目名称
        max_workers: 最大并行线程数
    
    Returns:
        包含所有case分析结果的字典，key为 "pr_num_method_name"
    """
    with open(json_file, 'r') as f:
        data = json.load(f)
    
    # 结果字典（线程安全）
    result = {}
    # result_lock = threading.Lock()
    
    # # 打印锁（保证输出不会被线程交错打乱）
    # print_lock = threading.Lock()
    
    def process_case(case):
        """处理单个case的覆盖率分析"""
        image = case["instance_id"]
        pr_num = image.split(':')[-1]
        method_name = case["method_name"]
        target_file_path = method_name.split('#')[0]
        test_file_path = case["test_file_path"]
        function_code = case["focal_method"]
        sub_dir_name = method_name.replace('/', '_')
        project_dir = f"/home/{project_name}"
        output_dir = f"coverage/{project_name}/{pr_num}/{sub_dir_name}"
        key = f"{pr_num}_{method_name}"


        # if pr_num != 'pr-1245':
        #     return key

        config = CoverageTestConfig(
            image_name=image,
            test_code=case["test_code"],
            test_file_path=test_file_path,
            method_name=method_name,
            function_code=function_code,
            project_name=project_name,
            project_dir=project_dir,
            output_dir=output_dir
        )

        if not skip_test:
            # 清空输出目录
            if os.path.exists(output_dir):
                shutil.rmtree(output_dir)
            os.makedirs(output_dir, exist_ok=True)
            runner = CoverageTestRunner(config)
            success = runner.run()
        
        if project_name in gradle_list:
            analyzer = GradleLogAnalyzer()
        else:
            analyzer = TestLogAnalyzer()
        
        run_log_path = f"{output_dir}/run.log"
        output_report = f"{output_dir}/coverage_report.txt"
        if project_name == 'guava':
            jacoco_dir = f"{output_dir}/jacoco-aggregate/guava"
        else:
            jacoco_dir = f"{output_dir}/jacoco"
        
        entry = analyze_run_log(analyzer, run_log_path, test_file_path)
        save_test_result_to_report(entry, output_report)
        # print(entry)
        if not os.path.exists(jacoco_dir):
            result[key] = entry
            return key
        
        report = generate_coverage_report(
            jacoco_dir=jacoco_dir,
            target_file=target_file_path,
            function_code=function_code,
            output_file=output_report
        )

        coverage_info = {
            "success": True,
            "function_name": report.function_name,
            "file_path": target_file_path,
            "start_line": report.start_line,
            "end_line": report.end_line,
            "instruction_coverage": report.coverage.instruction_coverage,
            "branch_coverage": report.coverage.branch_coverage,
            "line_coverage": report.coverage.line_coverage,
            "total_lines_num": report.coverage.total_lines_num,
            "missed_lines_num": report.coverage.missed_lines_num,
            "missed_lines": report.missed_lines
        }
        # 生成带注释的代码
        coverage_info["annotated_code"] = _annotate_uncovered_lines(
            function_code, report.missed_lines
        )
        entry["coverage_info"] = coverage_info
        
        # # 线程安全地写入结果
        # with result_lock:
        result[key] = entry
        
        # # 线程安全地打印
        # with print_lock:
        #     print(format_coverage_report(coverage_info))
        
        return key
    
    # 使用ThreadPoolExecutor并行执行
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # 提交所有任务
        futures = {executor.submit(process_case, case): case for case in data}
        
        # 收集完成的任务
        for future in as_completed(futures):
            case = futures[future]
            try:
                key = future.result()
                print(f"\n[{key}] 处理完成")
            except Exception as e:
                print(f"\n[{case['method_name']}] 执行失败: {e}")

    with open(f"{project_name}_coverage.json", 'w') as f:
        json.dump(result, f, indent=4)
    
    return result


def main():
    """主函数"""
    project_name = "fastjson2" # fastjson2 dubbo logstash jackson-databind jackson-core jackson-dataformat-xml gson jib mockito
    json_file = f"/data/gaoshutao/liuxinyin/LLM4pr_new/coverage/{project_name}.json"
    run_coverage_analysis(json_file, project_name, max_workers=1)


if __name__ == "__main__":
    main()
