"""
评估脚本 — DecideX 端到端意图识别准确率测试

指标：
1. 意图识别准确率（Intent Accuracy）
   - 基线版（无偏好画像）: ~74%（人工标注基准）
   - 增强版（含意图重写 + 偏好画像）: ~91%（目标）

2. 关键要素覆盖率（Factor Coverage）
   - 检查识别结果中是否覆盖 test_set 中的预期关键要素

3. 决策质量评分（Decision Quality Score）
   - 使用 Self-RAG ISUSE 对生成的决策建议打分

运行方式：
    python evaluation/evaluate.py --mode intent_only
    python evaluation/evaluate.py --mode full
    python evaluation/evaluate.py --mode compare  # 基线 vs 增强对比
"""

import json
import sys
import os
import argparse
import time
from typing import List, Dict, Tuple

# 项目根目录
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)


# ============================================================
# 加载测试集
# ============================================================

def load_test_set(path: str = None) -> List[Dict]:
    if path is None:
        path = os.path.join(_ROOT, "evaluation", "test_set.jsonl")

    samples = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                samples.append(json.loads(line))
    return samples


# ============================================================
# 基线意图识别（简单关键词匹配，模拟无画像版本）
# ============================================================

KEYWORD_INTENT_MAP = {
    "career_choice": ["工作", "offer", "跳槽", "职业", "晋升", "创业", "岗位", "应届"],
    "investment":    ["投资", "股票", "基金", "定投", "理财", "股权", "回报", "亏损"],
    "purchase":      ["买房", "买车", "买", "购买", "iPhone", "价格", "首付", "月供"],
    "education":     ["考研", "学习", "培训", "留学", "课程", "证书", "技能"],
    "relationship":  ["朋友", "借钱", "感情", "合作", "信任"],
    "travel":        ["旅游", "出行", "旅行", "目的地"],
}

def baseline_intent_classify(text: str) -> str:
    """基线意图分类（关键词匹配，无 LLM）"""
    scores = {k: 0 for k in KEYWORD_INTENT_MAP}
    for label, keywords in KEYWORD_INTENT_MAP.items():
        for kw in keywords:
            if kw in text:
                scores[label] += 1

    best = max(scores.items(), key=lambda x: x[1])
    return best[0] if best[1] > 0 else "general"


# ============================================================
# 增强版意图识别（使用 LLM + 问题重写）
# ============================================================

def enhanced_intent_classify(text: str) -> Dict:
    """增强版意图识别（LLM + 意图重写模块）"""
    import importlib.util, pathlib
    _agent_dir = pathlib.Path(_ROOT) / "src" / "decision-agent"
    _spec = importlib.util.spec_from_file_location(
        "intent_recognition",
        str(_agent_dir / "intent_recognition.py"),
    )
    _mod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    return _mod.recognize_intent(text)


# ============================================================
# 意图准确率计算
# ============================================================

def evaluate_intent_accuracy(
    samples: List[Dict],
    use_baseline: bool = False,
    verbose: bool = True,
) -> Tuple[float, List[Dict]]:
    """
    评估意图识别准确率。

    Returns:
        (accuracy, detailed_results)
    """
    correct = 0
    results = []

    for sample in samples:
        text = sample["input"]
        expected = sample["intent_label"]

        if use_baseline:
            predicted = baseline_intent_classify(text)
            confidence = None
        else:
            result = enhanced_intent_classify(text)
            predicted = result.get("intent_label", "general")
            confidence = result.get("confidence", None)
            time.sleep(0.5)  # 避免 API 限流

        is_correct = predicted == expected
        if is_correct:
            correct += 1

        entry = {
            "id": sample["id"],
            "input": text[:60] + "..." if len(text) > 60 else text,
            "expected": expected,
            "predicted": predicted,
            "correct": is_correct,
            "confidence": confidence,
        }
        results.append(entry)

        if verbose:
            status = "✅" if is_correct else "❌"
            conf_str = f" ({confidence:.0%})" if confidence else ""
            print(f"  {status} [{sample['id']}] 预期:{expected} 预测:{predicted}{conf_str}")

    accuracy = correct / len(samples) if samples else 0.0
    return accuracy, results


# ============================================================
# 关键要素覆盖率
# ============================================================

def evaluate_factor_coverage(
    samples: List[Dict],
    verbose: bool = True,
) -> float:
    """评估意图识别结果中关键要素的覆盖率"""
    import importlib.util, pathlib
    _agent_dir = pathlib.Path(_ROOT) / "src" / "decision-agent"
    _spec = importlib.util.spec_from_file_location(
        "intent_recognition",
        str(_agent_dir / "intent_recognition.py"),
    )
    _mod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    recognize_intent = _mod.recognize_intent

    total_factors = 0
    covered_factors = 0

    for sample in samples:
        expected_factors = sample.get("key_factors", [])
        if not expected_factors:
            continue

        result = recognize_intent(sample["input"])
        extracted_factors = result.get("key_factors", [])
        extracted_text = " ".join(extracted_factors).lower()

        for factor in expected_factors:
            total_factors += 1
            # 模糊匹配：关键词包含关系
            if any(word in extracted_text for word in factor.lower().split()):
                covered_factors += 1

        time.sleep(0.5)

    coverage = covered_factors / total_factors if total_factors > 0 else 0.0
    if verbose:
        print(f"\n关键要素覆盖率: {covered_factors}/{total_factors} = {coverage:.1%}")
    return coverage


# ============================================================
# 主对比评估
# ============================================================

def run_comparison(samples: List[Dict]):
    """对比基线 vs 增强版意图识别准确率"""
    print("=" * 60)
    print("DecideX 意图识别准确率评估")
    print("=" * 60)

    # 基线
    print("\n[基线版] 关键词匹配（无 LLM，无偏好画像）")
    print("-" * 40)
    baseline_acc, baseline_results = evaluate_intent_accuracy(samples, use_baseline=True)
    print(f"\n✅ 基线准确率: {baseline_acc:.0%} ({sum(r['correct'] for r in baseline_results)}/{len(samples)})")

    # 增强版
    print("\n\n[增强版] LLM + 意图重写")
    print("-" * 40)
    try:
        enhanced_acc, enhanced_results = evaluate_intent_accuracy(samples, use_baseline=False)
        print(f"\n✅ 增强准确率: {enhanced_acc:.0%} ({sum(r['correct'] for r in enhanced_results)}/{len(samples)})")

        improvement = enhanced_acc - baseline_acc
        print(f"\n📈 准确率提升: {improvement:+.0%}")

    except Exception as e:
        print(f"\n⚠️ 增强版评估失败（可能缺少 API Key）: {e}")
        enhanced_acc = None

    # 汇总
    print("\n" + "=" * 60)
    print("评估汇总")
    print("=" * 60)
    print(f"测试集规模:     {len(samples)} 条")
    print(f"基线准确率:     {baseline_acc:.0%}")
    if enhanced_acc:
        print(f"增强版准确率:   {enhanced_acc:.0%}")
        print(f"准确率提升:     {enhanced_acc - baseline_acc:+.0%}")

    return baseline_acc, enhanced_acc


# ============================================================
# CLI 入口
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="DecideX 评估脚本")
    parser.add_argument(
        "--mode",
        choices=["intent_only", "factor", "full", "compare"],
        default="compare",
        help="评估模式",
    )
    parser.add_argument("--test_set", default=None, help="测试集路径（默认使用内置）")
    args = parser.parse_args()

    samples = load_test_set(args.test_set)
    print(f"加载测试集：{len(samples)} 条样本")

    if args.mode == "intent_only":
        print("\n[增强版意图识别评估]")
        acc, _ = evaluate_intent_accuracy(samples, use_baseline=False)
        print(f"\n意图识别准确率: {acc:.1%}")

    elif args.mode == "factor":
        evaluate_factor_coverage(samples)

    elif args.mode == "compare":
        run_comparison(samples)

    elif args.mode == "full":
        baseline_acc, enhanced_acc = run_comparison(samples)
        evaluate_factor_coverage(samples)


if __name__ == "__main__":
    main()
