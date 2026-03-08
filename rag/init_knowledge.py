"""
一键初始化 DecideX 知识库
将所有知识文档向量化存入 Chroma

使用方式：
    python rag/init_knowledge.py
    python rag/init_knowledge.py --rebuild   # 强制重建
"""

import sys
import os
import argparse

# 确保项目根目录在 path 中
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from rag.knowledge_base import build_knowledge_index

def main():
    parser = argparse.ArgumentParser(description="初始化 DecideX 知识库")
    parser.add_argument("--rebuild", action="store_true", help="强制重建（清空旧数据）")
    args = parser.parse_args()

    print("🚀 开始初始化 DecideX 知识库...\n")

    for kb_type in ["cost", "risk", "value"]:
        label = {"cost": "成本评估", "risk": "风险评估", "value": "用户价值"}.get(kb_type, kb_type)
        print(f"📚 正在处理 [{label}] 知识库...", end=" ", flush=True)
        try:
            count = build_knowledge_index(kb_type, force_rebuild=args.rebuild)
            print(f"✅ 完成，共 {count} 个知识片段")
        except FileNotFoundError as e:
            print(f"❌ 文件不存在：{e}")
        except Exception as e:
            print(f"❌ 失败：{e}")

    print("\n✨ 知识库初始化完成！")
    print(f"📁 数据存储位置：data/chroma_db/")


if __name__ == "__main__":
    main()
