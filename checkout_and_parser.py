import subprocess
import os
import sys
import json
import tempfile
from parser_main import parser_main

def checkout_and_parse(project_root, dataset_path, sha, output_path, pr_number, fix_patch):
    """
    切换项目版本并调用解析函数
    
    Args:
        project_root: 项目代码根目录
        dataset_path: 原始数据集文件路径
        project_id: 项目ID
        sha: git sha值
    """
    try:
        # 切换到项目根目录
        original_cwd = os.getcwd()
        print(f"切换到项目目录: {project_root}")
        os.chdir(project_root)

        # 添加git安全目录配置（解决所有权问题）
        print("配置git安全目录...")
        safe_dir_result = subprocess.run(
            ["git", "config", "--global", "--add", "safe.directory", project_root],
            capture_output=True,
            text=True
        )
        
        if safe_dir_result.returncode != 0:
            print(f"警告: 无法添加安全目录: {safe_dir_result.stderr}")
            return False
        
        # 2. 使用git checkout切换到指定版本
        print(f"正在切换到sha: {sha}")
        checkout_result = subprocess.run(
            ["git", "checkout", "-f", sha],
            capture_output=True,
            text=True
        )
        
        if checkout_result.returncode != 0:
            print(f"Git checkout失败: {checkout_result.stderr}")
            return False
        
        print(f"成功切换到sha: {sha}")
        print(f"Git checkout输出: {checkout_result.stdout}")
        
        print(f"正在清理未绑定的文件:")
        clean_result = subprocess.run(
            ["git", "clean", "-f", "-d"],
            capture_output=True,
            text=True
        )
        
        if clean_result.returncode != 0:
            print(f"Git checkout失败: {clean_result.stderr}")
            return False
        
        print(f"clean输出: {clean_result.stdout}")
        
        # 3. 验证是否切换成功
        verify_result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True
        )
        current_sha = verify_result.stdout.strip()
        print(f"当前HEAD: {current_sha}")
        
        if current_sha != sha:
            print(f"警告: 当前HEAD({current_sha})与目标sha({sha})不匹配")
            
        if fix_patch:
            print("正在应用fix_patch补丁...")
            # 将补丁内容写入临时文件
            with tempfile.NamedTemporaryFile(mode='w', suffix='.patch', delete=False) as patch_file:
                patch_file.write(fix_patch)
                patch_path = patch_file.name
            try:
                # 执行git apply
                apply_result = subprocess.run(
                    ["git", "apply", "--verbose", patch_path],
                    capture_output=True,
                    text=True
                )
                if apply_result.returncode != 0:
                    print(f"应用补丁失败: {apply_result.stderr}")
                    return False
                else:
                    print("补丁应用成功")
            finally:
                # 删除临时文件
                os.unlink(patch_path)
        
        # 4. 返回到原始目录
        os.chdir(original_cwd)
        
        # 5. 调用parser_main函数
        print(f"调用parser_main函数...")
        print(f"  输出文件: {output_path}")
        
        # 调用您的parser_main函数
        # 注意: 这里假设parser_main已经在当前作用域中定义
        result = parser_main(project_root, dataset_path, output_path, pr_number)
        
        print(f"parser_main执行完成")
        return result
        
    except Exception as e:
        print(f"执行过程中发生错误: {str(e)}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # 确保返回到原始目录
        if 'original_cwd' in locals():
            os.chdir(original_cwd)

if __name__=="__main__":
    # 修改参数
    org_name = "alibaba" #apache google alibaba apache elastic fasterxml fasterxml fasterxml google googlecontainertools mockito alibaba apache
    project_name = "fastjson2" #commons-lang guava fastjson2 dubbo logstash jackson-databind jackson-core jackson-dataformat-xml gson jib mockito nacos skywalking
    raw_data_path = f"./multi_swe_bench/tmp/raw_dataset/{org_name}__{project_name}_dataset.jsonl"
    project_root = f"./multi_swe_bench/tmp/repos/{org_name}/{project_name}/"
    with open(raw_data_path, 'r') as f:
        for line in f:
            content = json.loads(line)
            repo = content["repo"]
            pr_number = content["number"]
            output_file = f"./context_graph/{repo}_{pr_number}.pkl"
            if os.path.exists(output_file):
                continue
            sha = content["base"]["sha"]
            fix_patch = content["fix_patch"]
            checkout_and_parse(project_root, raw_data_path, sha, output_file, pr_number, fix_patch)