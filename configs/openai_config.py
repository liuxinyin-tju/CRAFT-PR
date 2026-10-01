import json
import time
from openai import OpenAI

# 手工修改这里即可，后续不用在各个文件里重复修改。
OPENAI_API_KEY = "sk-rlkeaehxxfruejtastyixgvgyhbzergotpvrjbqgjndcbaza" # sk-rlkeaehxxfruejtastyixgvgyhbzergotpvrjbqgjndcbaza sk-OM2wrzDT76GmRQreeJYH494Wupsqqi0WC7ZwSmklMpOenlFZ
OPENAI_BASE_URL = "https://api.siliconflow.cn/v1" # https://api.siliconflow.cn/v1 https://quanzil.com/v1
OPENAI_MODEL = "deepseek-ai/DeepSeek-V3.2" #deepseek-ai/DeepSeek-V3.2 gpt-5 Qwen/Qwen3.5-397B-A17B


def get_openai_api_key():
    return OPENAI_API_KEY


def get_openai_base_url():
    return OPENAI_BASE_URL


def get_openai_model():
    return OPENAI_MODEL


def build_openai_client(api_key=None, base_url=None):
    return OpenAI(
        api_key=api_key or get_openai_api_key(),
        base_url=base_url or get_openai_base_url(),
    )


class TokenUsageCollector:
    """全局大模型 token 消耗收集器，按阶段和 case 记录每次调用的 usage。"""

    def __init__(self):
        self.records = []  # 每次 LLM 调用的明细

    def reset(self):
        """清空所有记录（每个 project/turn 开始时调用）。"""
        self.records = []

    def add_usage(self, stage, instance_id, method_name, usage, model=None, duration=0.0):
        """
        记录一次 LLM 调用的 token 用量和耗时。

        Args:
            stage: 阶段标识，如 "gen" / "repair" / "strengthen"
            instance_id: 用例实例 ID
            method_name: 方法名
            usage: OpenAI response.usage 对象（含 prompt_tokens / completion_tokens / total_tokens）
            model: 模型名（可选）
            duration: 本次模型调用耗时（秒）
        """
        if usage is None:
            return
        record = {
            "stage": stage,
            "instance_id": instance_id or "",
            "method_name": method_name or "",
            "model": model or "",
            "prompt_tokens": getattr(usage, "prompt_tokens", 0) or 0,
            "completion_tokens": getattr(usage, "completion_tokens", 0) or 0,
            "total_tokens": getattr(usage, "total_tokens", 0) or 0,
            "duration": round(duration, 4),
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        self.records.append(record)

    def summary_by_stage(self):
        """按阶段汇总 token 用量和耗时。"""
        summary = {}
        for r in self.records:
            stage = r["stage"]
            if stage not in summary:
                summary[stage] = {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "call_count": 0,
                    "total_duration": 0.0,
                }
            summary[stage]["prompt_tokens"] += r["prompt_tokens"]
            summary[stage]["completion_tokens"] += r["completion_tokens"]
            summary[stage]["total_tokens"] += r["total_tokens"]
            summary[stage]["call_count"] += 1
            summary[stage]["total_duration"] += r["duration"]
        # 计算平均耗时
        for s in summary.values():
            s["avg_duration"] = round(s["total_duration"] / s["call_count"], 4) if s["call_count"] > 0 else 0.0
            s["total_duration"] = round(s["total_duration"], 4)
        return summary

    def total_summary(self):
        """全流程 token 汇总。"""
        total = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "call_count": 0, "total_duration": 0.0}
        for r in self.records:
            total["prompt_tokens"] += r["prompt_tokens"]
            total["completion_tokens"] += r["completion_tokens"]
            total["total_tokens"] += r["total_tokens"]
            total["call_count"] += 1
            total["total_duration"] += r["duration"]
        total["avg_duration"] = round(total["total_duration"] / total["call_count"], 4) if total["call_count"] > 0 else 0.0
        total["total_duration"] = round(total["total_duration"], 4)
        return total

    def print_summary(self):
        """打印 token 汇总到控制台。"""
        print("\n" + "=" * 60)
        print("📊 Token 消耗与模型调用耗时汇总")
        print("=" * 60)
        for stage, s in self.summary_by_stage().items():
            print(f"  [{stage}] 调用次数: {s['call_count']}, "
                  f"prompt: {s['prompt_tokens']}, "
                  f"completion: {s['completion_tokens']}, "
                  f"total: {s['total_tokens']}, "
                  f"耗时: {s['total_duration']}s (平均 {s['avg_duration']}s)")
        total = self.total_summary()
        print("-" * 60)
        print(f"  总计: 调用次数 {total['call_count']}, "
              f"prompt: {total['prompt_tokens']}, "
              f"completion: {total['completion_tokens']}, "
              f"total: {total['total_tokens']}, "
              f"耗时: {total['total_duration']}s (平均 {total['avg_duration']}s)")
        print("=" * 60 + "\n")

    def save_to_file(self, file_path):
        """将明细和汇总保存为 JSON 文件。"""
        data = {
            "summary_by_stage": self.summary_by_stage(),
            "total": self.total_summary(),
            "records": self.records,
        }
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"💾 Token 用量已保存到: {file_path}")


# 全局单例，各模块直接导入使用
token_collector = TokenUsageCollector()
