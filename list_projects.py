import json
from pathlib import Path

import requests

GNS3_SERVER = "http://127.0.0.1:3080/v2"
OUTPUT_FILE = Path(__file__).with_name("local_projects.json")

print("=" * 60)
print("GNS3 项目列表")
print("=" * 60)

try:
    r = requests.get(f"{GNS3_SERVER}/projects")
    if r.status_code != 200:
        print(f"❌ 请求失败: {r.status_code}")
        exit(1)
    
    projects = r.json()

    with OUTPUT_FILE.open("w", encoding="utf-8") as file:
        json.dump(projects, file, ensure_ascii=False, indent=2)

    print(f"已将 {len(projects)} 个项目保存至: {OUTPUT_FILE}")
    print("=" * 60)

except requests.exceptions.ConnectionError:
    print("❌ 无法连接到服务器")
    print("请检查GNS3服务器是否运行")
except Exception as e:
    print(f"❌ 错误: {e}")
