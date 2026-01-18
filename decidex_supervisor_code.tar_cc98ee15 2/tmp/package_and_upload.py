#!/usr/bin/env python3
import os
import shutil
from pathlib import Path
from coze_coding_dev_sdk.s3 import S3SyncStorage

def create_zip_package():
    """创建 zip 压缩包"""
    import zipfile

    source_dir = Path("/tmp/decidex_risk_agent")
    output_file = Path("/tmp/decidex_risk_agent.zip")

    with zipfile.ZipFile(output_file, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for file_path in source_dir.rglob('*'):
            if file_path.is_file():
                arcname = file_path.relative_to(source_dir)
                zipf.write(file_path, arcname)

    return output_file

def upload_to_storage(zip_path):
    """上传到对象存储"""
    storage = S3SyncStorage(
        endpoint_url=os.getenv("COZE_BUCKET_ENDPOINT_URL"),
        access_key="",
        secret_key="",
        bucket_name=os.getenv("COZE_BUCKET_NAME"),
        region="cn-beijing",
    )

    # 读取文件内容
    with open(zip_path, 'rb') as f:
        file_content = f.read()

    # 上传文件
    file_key = storage.upload_file(
        file_content=file_content,
        file_name="decidex_risk_agent.zip",
        content_type="application/zip",
    )

    # 生成下载链接（有效期 24 小时）
    download_url = storage.generate_presigned_url(
        key=file_key,
        expire_time=86400  # 24 小时
    )

    return file_key, download_url

if __name__ == "__main__":
    print("📦 正在打包代码...")
    zip_path = create_zip_package()
    print(f"✅ 打包完成: {zip_path}")
    print(f"📊 文件大小: {zip_path.stat().st_size / 1024:.2f} KB")

    print("\n📤 正在上传到对象存储...")
    file_key, download_url = upload_to_storage(zip_path)
    print(f"✅ 上传成功!")
    print(f"📁 文件 Key: {file_key}")
    print(f"\n🔗 下载链接 (24小时有效):")
    print(f"{download_url}")
