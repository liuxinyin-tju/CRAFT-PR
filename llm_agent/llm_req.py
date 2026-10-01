import json
import time
from typing import Dict
import os

from configs.openai_config import build_openai_client, get_openai_model


class RequirementGenerator:
    def __init__(self, api_key: str = None):
        self.client = build_openai_client(api_key=api_key)
        self.model = get_openai_model()
        
    def generate_instruction(self, requirement: str, pull_request: str, fix_patch: str, file_function_pairs: list, max_retries: int = 3) -> Dict:
        
        prompt = f"""        
        Role: You are a senior technical requirements analyst with extensive experience in software development and system design. You excel at transforming ambiguous raw requirements or code snippets into clear, structured, and executable technical requirement documents.
        
        Task: Based on the original requirement, pull_request, patch, and file_function_pairs provided, generate a high-quality, structurally complete, and logically rigorous requirements analysis document. The document must comprehensively cover the five core modules, presented in natural, fluent, concise, and accurate language in English. The final output must be returned strictly in the specified JSON format.
        
        Note that when describing technical implementations, or solutions, retain and embed actual code snippets from the requirement when they are essential to understanding the technical approach.
        
        1. Method Summary: Describe the core functionalities of the focal method from file_function_pairs.
        
        2. Requirement Description: Elaborate on the core need this requirement aims to address. Clearly explain the requirement itself and the current system behavior.
        
        3. Trigger Scenario: Specify under what scenarios this requirement will be triggered. This may include the calling code method or API, input parameters or data structures, specific steps of code execution, and location information (optional).
        
        4. Expected Outcome: Describe the correct and unambiguous expected behavior from the patch the system should exhibit after the requirement is properly implemented in the aforementioned scenario.
        
        5. Solution: Describe the correct solution from the patch for implementing the requirement in the aforementioned scenario. 

        【Output format (JSON)】
        Please return strictly in the following JSON format without any additional information!!!
        {{
            "method_summary": "[text which describe the core functionalities of the focal method using natural language.]",
            "requirement_description": "[text with embedded ```code blocks``` where needed]",
            "trigger_scenario": "[text with embedded ```code blocks``` where needed]",
            "expected_outcome": "[text with embedded ```code blocks``` where needed]",
            "solution": "[text with embedded ```code blocks``` where needed]"
        }}
        
        【Input resource】
        The original requirement (Refers to the unprocessed initial task description containing the user-reported problem or desired feature) is as follows: {requirement}
        The pull_request (Refers to the formal code change proposal, including description, changes, and review context that addresses the issue) is as follows: {pull_request}
        The patch (Refers to the complete, correct code implementation that fixes the defect and fulfills the requirement) is as follows: {fix_patch}
        The file_function_pairs (a list containing information directly associated with the patch, including file paths, classes, modified functions, sibling functions, functions called within methods, and other relevant code from the repaired version) is as follows: {file_function_pairs}
        """
        
        for attempt in range(max_retries):
            try:
                response = self.client.chat.completions.create(
                    model = self.model,
                    messages = [
                        {"role": "system", "content": "You are a senior technical requirements analyst with extensive experience in software development and system design."},
                        {"role": "user", "content": prompt}
                    ],
                    stream = False
                )
                content = response.choices[0].message.content
                
                if content.startswith("```json"):
                    content = content.lstrip("```json").rstrip("```").strip()
                elif content.startswith("```"):
                    content = content.lstrip("```").rstrip("```").strip()
                
                data = json.loads(content)
                # 验证必需字段
                if not all(key in data for key in ["method_summary", "requirement_description", "trigger_scenario", "expected_outcome", "solution"]):
                    raise ValueError("响应缺少必需字段")
                return data

            except Exception as e:
                print(f"API调用失败 (尝试 {attempt + 1}/{max_retries}): {e}")
                time.sleep(2)
                continue
        return None


if __name__ == "__main__":
    # "elastic_logstash.json",
    dataset_list = [
        # "test.json"
        # "dubbo.json",
        "fastjson2.json",
        # "gson.json",
        # "jackson-core.json",
        # "jackson-databind.json",
        # "jackson-dataformat-xml.json"
        # "logstash.json"
        # "nacos.json"
        # "skywalking.json"
        # "guava.json"
    ]
    current_time = time.localtime()
    # 格式化输出
    formatted_time = time.strftime("%Y-%m-%d %H:%M:%S", current_time)
    print("当前时间:", formatted_time)
    # focal_method  test_file_path
    for dataset in dataset_list:
        input_file = "./locate/results_with_context/" + dataset
        output_file = "./locate/results_with_requirement/" + dataset
        structured_requirements = []
        if os.path.exists(output_file):
            with open(output_file, 'r') as f:
                structured_requirements = json.load(f)
        generator = RequirementGenerator()
        with open(input_file, 'r', encoding='utf-8') as file:
            items = json.load(file)
        for item in items:
            if any(existing_item['org'] == item['org'] and existing_item['repo'] == item['repo'] and existing_item['number'] == item['number'] for existing_item in structured_requirements):
                print(f"{item['org']}/{item['repo']}/{item['number']} already exists, skipping...")
                continue
            requirement = item["resolved_issues"][0]["title"] + "\n" + item["resolved_issues"][0]["body"]
            pull_request = f"{item['title']}\n{item['body']}"
            fix_patch = item["fix_patch"]
            file_function_pairs = item["file_function_pairs"]
            result = generator.generate_instruction(requirement = requirement, pull_request = pull_request, fix_patch = fix_patch, file_function_pairs = file_function_pairs)
            if result is not None:
                item["structured_requirements"] = {"method_summary": result["method_summary"], "requirement_description": result["requirement_description"], "trigger_scenario": result["trigger_scenario"], "expected_outcome": result["expected_outcome"], "solution": result["solution"]}       
            else:
                item["structured_requirements"] = {"method_summary": "", "requirement_description": "", "trigger_scenario": "", "expected_outcome": "", "solution": ""}
                print(f"{item['org']}/{item['repo']}/{item['number']} is none is none !!!")
            structured_requirements.append(item)
            # print(f"{item['org']}/{item['repo']}/{item['number']} finish!!!")
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(structured_requirements, f, ensure_ascii=False, indent=2)
            
    current_time = time.localtime()
    # 格式化输出
    formatted_time = time.strftime("%Y-%m-%d %H:%M:%S", current_time)
    print("当前时间:", formatted_time)
