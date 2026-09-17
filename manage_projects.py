import requests
import json

GNS3_SERVER = "http://127.0.0.1:3080/v2"

print("=" * 60)
print("GNS3 项目管理")
print("=" * 60)

r = requests.get(f"{GNS3_SERVER}/projects")
projects = r.json()

print("\n项目列表:\n")
for i, p in enumerate(projects, 1):
    status = "🟢 运行中" if p.get('status') == 'started' else "🔴 已停止"
    print(f"{i}. {p['name']}")
    print(f"   ID: {p['project_id']}")
    print(f"   状态: {status}")
    print()

print("-" * 60)
print("输入项目编号进行操作 (输入数字)")
print("  [d] 删除项目")
print("  [s] 停止项目")
print("  [q] 退出")
print("-" * 60)

choice = input("\n请选择: ").strip().lower()

if choice.isdigit():
    idx = int(choice) - 1
    if 0 <= idx < len(projects):
        p = projects[idx]
        action = input(f"对项目 '{p['name']}' 执行什么操作? [d=删除, s=停止]: ").strip().lower()
        
        project_id = p['project_id']
        
        if action == 'd':
            if p.get('status') == 'started':
                print("正在停止项目...")
                r = requests.post(f"{GNS3_SERVER}/projects/{project_id}/stop")
                print(f"停止响应: {r.status_code}")
            
            print("正在删除项目...")
            r = requests.delete(f"{GNS3_SERVER}/projects/{project_id}")
            print(f"删除响应: {r.status_code}, {r.text[:200]}")
            
            if r.status_code == 204:
                print(f"✅ 项目 '{p['name']}' 已删除")
            elif r.status_code == 409:
                print("⚠️  409错误: 项目可能被锁定或文件缺失")
                print("尝试强制删除...")
                r = requests.delete(f"{GNS3_SERVER}/projects/{project_id}?force=true")
                if r.status_code == 204:
                    print(f"✅ 强制删除成功!")
                else:
                    print(f"❌ 强制删除也失败: {r.status_code}")
                    print(f"错误信息: {r.text}")
            else:
                print(f"❌ 删除失败: {r.status_code}")
        
        elif action == 's':
            if p.get('status') == 'started':
                r = requests.post(f"{GNS3_SERVER}/projects/{project_id}/stop")
                if r.status_code == 200:
                    print(f"✅ 项目已停止")
            else:
                print("项目已经在停止状态")
    
elif choice == 'q':
    print("退出")
