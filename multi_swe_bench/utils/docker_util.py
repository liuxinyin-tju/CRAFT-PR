# Copyright (c) 2024 Bytedance Ltd. and/or its affiliates

#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at

#      http://www.apache.org/licenses/LICENSE-2.0

#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

import logging
from pathlib import Path
from typing import Optional, Union
import os
import json

import docker

docker_client = docker.from_env()


def exists(image_name: str) -> bool:
    try:
        docker_client.images.get(image_name)
        return True
    except docker.errors.ImageNotFound:
        return False


def build(
    workdir: Path, dockerfile_name: str, image_full_name: str, logger: logging.Logger
):
    workdir = str(workdir)
    logger.info(
        f"Start building image `{image_full_name}`, working directory is `{workdir}`"
    )
    try:
        print(
            "docker_client: ",
            docker_client.api,
            "\n",
            "workdir: ",
            workdir,
            "\n",
            "dockerfile_name: ",
            dockerfile_name,
            "\n",
            "image_full_name: ",
            image_full_name,
        )
        # exit()
        build_logs = docker_client.api.build(
            path=workdir,
            dockerfile=dockerfile_name,
            tag=image_full_name,
            rm=True,
            forcerm=True,
            decode=True,
            encoding="utf-8",
        )

        for log in build_logs:
            if "stream" in log:
                logger.info(log["stream"].strip())
            elif "error" in log:
                error_message = log["error"].strip()
                logger.error(f"Docker build error: {error_message}")
                raise RuntimeError(f"Docker build failed: {error_message}")
            elif "status" in log:
                logger.info(log["status"].strip())
            elif "aux" in log:
                logger.info(log["aux"].get("ID", "").strip())

        logger.info(f"image({workdir}) build success: {image_full_name}")
    except docker.errors.BuildError as e:
        logger.error(f"build error: {e}")
        raise e
    except Exception as e:
        logger.error(f"Unknown build error occurred: {e}")
        raise e


def run(
    image_full_name: str,
    run_command: str,
    output_path: Optional[Path] = None,
    global_env: Optional[list[str]] = None,
    volumes: Optional[Union[dict[str, str], list[str]]] = None,
    test_code: str = "",
    test_file_path: str = "",
    method_name: str = "",
) -> str:
    container = None
    try:
        file_dir = os.path.dirname(test_file_path)
        file_name = os.path.basename(test_file_path)
        escaped_code = json.dumps(test_code)
        if 'guava' in image_full_name:
            command = rf"""
    sed -i.bak 's/\.\/mvnw test -Dmaven\.test\.skip=false -DfailIfNoTests=false --fail-at-end/\.\/mvnw install -Dmaven\.test\.skip=false -DfailIfNoTests=false --fail-at-end/g' /home/fix-run.sh
    cd {file_dir}
    echo -e {escaped_code} > {file_name}
    {run_command}
    """
        else:    
            command = rf"""
    cd {file_dir}
    echo -e {escaped_code} > {file_name}
    {run_command}
    """
        # find . -type d -name "test" -exec find {{}} -type f -name "*.java" -delete \;

        container = docker_client.containers.run(
            image=image_full_name,
            command=["bash", "-c", command],
            remove=False,
            detach=True,
            stdout=True,
            stderr=True,
            environment=global_env,
            volumes=volumes,
        )

        output = ""
        index = method_name.replace("/", "_").replace(".", "")
        if output_path:
            file_name = output_path.name
            file_dir = output_path.parent
            new_file_name = (
                file_name.split(".")[0] + f"_{index}." + file_name.split(".")[1]
            )
            output_path = file_dir / new_file_name
            with open(output_path, "w", encoding="utf-8") as f:
                for line in container.logs(stream=True, follow=True):
                    line_decoded = line.decode("utf-8")
                    f.write(line_decoded)
                    output += line_decoded
        else:
            container.wait()
            output = container.logs().decode("utf-8")

        return output
    finally:
        if container:
            try:
                # 先尝试停止容器（可选，增加成功率）
                try:
                    container.stop(timeout=10)
                except Exception:
                    pass
                container.remove(force=True)
            except Exception as e:
                print(f"Warning: Failed to remove container: {e}")
