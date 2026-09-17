import requests
import json
from datetime import datetime

GNS3_SERVER = "http://127.0.0.1:3080/v2"

project_id = None
project_name = None

def cleanup_on_failure():
    global project_id, project_name
    if project_id:
        print("\n⚠️  操作失败，正在清理...")
        try:
            r = requests.get(f"{GNS3_SERVER}/projects/{project_id}")
            if r.status_code == 200:
                proj = r.json()
                if proj.get('status') == 'started':
                    requests.post(f"{GNS3_SERVER}/projects/{project_id}/stop")
                requests.delete(f"{GNS3_SERVER}/projects/{project_id}")
                print(f"✅ 已清理项目: {project_name}")
        except Exception as e:
            print(f"⚠️  清理失败: {e}")

try:
    r = requests.get(f"{GNS3_SERVER}/templates")
    templates = r.json()
    print(f"✅ 找到 {len(templates)} 个模板")

    print("\n检查Compute节点...")
    r = requests.get(f"{GNS3_SERVER}/computes")
    gns3_vm_compute_id = None
    if r.status_code == 200:
        computes = r.json()
        for c in computes:
            print(f"{c.get('compute_id')}: {c.get('host')}")
            if 'dynamips' in c.get('capabilities', []):
                print(f"     - 支持 Dynamips")
            if 'qemu' in c.get('capabilities', []):
                print(f"     - 支持 QEMU")
            compute_id = c.get('compute_id', '')
            if compute_id == 'vm' or 'gns3 vm' in c.get('host', '').lower():
                gns3_vm_compute_id = compute_id
                print(f"     - 找到 GNS3 VM: {compute_id}")

except requests.exceptions.ConnectionError:
    print("❌ 无法连接到服务器，请检查GNS3是否运行")
    exit(1)

qemu_templates = []
docker_templates = []
host_templates = []
switch_templates = []
router_templates = []

for t in templates:
    cat = t.get('category', '').lower()
    name = t.get('name', '').lower()
    tp = t.get('template_type', '').lower()
    
    if cat == 'switch':
        switch_templates.append(t)
    
    if tp == 'vpcs':
        host_templates.append(t)
    elif tp == 'qemu':
        qemu_templates.append(t)
    elif tp == 'docker':
        docker_templates.append(t)
    elif tp == 'dynamips':
        router_templates.append(t)

if not host_templates:
    print("❌ 没有找到可用模板")
    exit(1)

node_tpl = host_templates[0]
print(f"将使用模板: {node_tpl['name']} ({node_tpl.get('template_type')})")

if qemu_templates:
    print(f"可用QEMU模板: {qemu_templates[0]['name']} ({qemu_templates[0].get('template_type')})")
if docker_templates:
    print(f"可用Docker模板: {docker_templates[0]['name']} ({docker_templates[0].get('template_type')})")
if router_templates:
    print(f"可用Router模板: {router_templates[0]['name']} ({router_templates[0].get('template_type')})")

project_name = f"TestLab_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
project_data = {"name": project_name}
r = requests.post(f"{GNS3_SERVER}/projects", json=project_data)

if r.status_code != 201:
    print(f"❌ 项目创建失败: {r.status_code}")
    print(f"错误详情: {r.text}")
    exit(1)

project = r.json()
if "project_id" not in project:
    print("❌ 响应中没有project_id")
    exit(1)

project_id = project["project_id"]
print(f"✅ 项目创建成功: {project_name} (ID: {project_id})")

try:
    print(f"\n[1] 创建VPCS节点 PC1...")
    template_type = node_tpl.get("template_type", "vpcs")
    compute_id = gns3_vm_compute_id if gns3_vm_compute_id else (node_tpl.get("compute_id") or "local")
    print(f"将使用Compute: {compute_id}")
    
    node_data = {
        "name": "PC1",
        "template_id": node_tpl["template_id"],
        "node_type": template_type,
        "compute_id": compute_id,
        "symbol": node_tpl.get("symbol"),
        "properties": node_tpl.get("properties", {}),
        "x": 150,
        "y": 200
    }
    
    print(f"发送数据: {json.dumps(node_data)}")
    r = requests.post(f"{GNS3_SERVER}/projects/{project_id}/nodes", json=node_data)
    if r.status_code != 201:
        print(f"❌ 创建节点失败: {r.status_code}")
        print(f"错误详情: {r.text}")
        cleanup_on_failure()
        exit(1)
    node1 = r.json()
    node1_id = node1["node_id"]
    print(f"✅ PC1 创建成功: {node1_id}")

    if qemu_templates:
        print(f"\n[2] 创建QEMU节点...")
        qemu_tpl = qemu_templates[0]
        qemu_props = qemu_tpl.get("properties", {})
        qemu_data = {
            "name": "QEMU1",
            "template_id": qemu_tpl["template_id"],
            "node_type": qemu_tpl.get("template_type", "qemu"),
            "compute_id": gns3_vm_compute_id if gns3_vm_compute_id else "local",
            "symbol": qemu_tpl.get("symbol", ":/symbols/qemu_guest.svg"),
            "properties": {
                "qemu_path": qemu_props.get("qemu_path", "/usr/bin/qemu-system-x86_64"),
                "console_type": qemu_props.get("console_type", "telnet")
            },
            "x": 450,
            "y": 150
        }
        print(f"发送数据: {json.dumps(qemu_data)}")
        r = requests.post(f"{GNS3_SERVER}/projects/{project_id}/nodes", json=qemu_data)
        if r.status_code != 201:
            print(f"❌ 创建QEMU节点失败: {r.status_code}")
            print(f"错误详情: {r.text}")
            cleanup_on_failure()
            exit(1)
        else:
            qemu_node = r.json()
            qemu_id = qemu_node["node_id"]
            print(f"✅ QEMU1 创建成功: {qemu_id}")

    if docker_templates:
        print(f"\n[3] 创建Docker节点...")
        docker_tpl = docker_templates[0]
        docker_props = docker_tpl.get("properties", {})
        
        docker_data = {
            "name": "Docker1",
            "template_id": docker_tpl["template_id"],
            "node_type": docker_tpl.get("template_type", "docker"),
            "compute_id": gns3_vm_compute_id if gns3_vm_compute_id else "local",
            "symbol": docker_tpl.get("symbol", ":/symbols/docker_guest.svg"),
            "properties": {
                "image": docker_props.get("image", "gns3/ubuntu:noble"),
                "console_type": docker_props.get("console_type", "telnet")
            },
            "x": 450,
            "y": 300,
        }
        
        print(f"发送数据: {json.dumps(docker_data)}")
        
        docker_url = f"{GNS3_SERVER}/projects/{project_id}/nodes"
        print(f"使用Docker API: {docker_url}")
        
        r = requests.post(docker_url, json=docker_data)
        if r.status_code != 201:
            print(f"❌ 创建Docker节点失败: {r.status_code}")
            print(f"错误详情: {r.text}")
            cleanup_on_failure()
            exit(1)
        else:
            docker_node = r.json()
            docker_id = docker_node["node_id"]
            print(f"✅ Docker1 创建成功: {docker_id}")

    if router_templates:
        print(f"\n[4] 创建Router节点...")
        router_tpl = router_templates[0]
        router_props = router_tpl.get("properties", {})
        
        router_data = {
            "name": "Router1",
            "template_id": router_tpl["template_id"],
            "node_type": router_tpl.get("template_type", "dynamips"),
            "compute_id": gns3_vm_compute_id if gns3_vm_compute_id else "local",
            "symbol": router_tpl.get("symbol", ":/symbols/router.svg"),
            "properties": {
                "console_type": router_props.get("console_type", "telnet"),
                "platform": router_props.get("platform", "c3745"),
                "image" : "c3745-adventerprisek9-mz.124-15.T14.image",
                "ram" : 256,
                "slot0": router_props.get("slot0", "GT96100-FE"),
                "slot1": router_props.get("slot2", "NM-1FE-TX"),
                "wic0": "WIC-2T",
                "wic1": "WIC-2T",
                "wic2": "WIC-2T",
            },
            "x": 300,
            "y": 250,
        }
        
        print(f"发送数据: {json.dumps(router_data)}")
        
        router_url = f"{GNS3_SERVER}/projects/{project_id}/nodes"
        print(f"使用Router API: {router_url}")
        
        r = requests.post(router_url, json=router_data)
        if r.status_code != 201:
            print(f"❌ 创建Router节点失败: {r.status_code}")
            print(f"错误详情: {r.text}")
            cleanup_on_failure()
            exit(1)
        else:
            router_node = r.json()
            router_id = router_node["node_id"]
            print(f"✅ Router1 创建成功: {router_id}")

    if switch_templates:
        print(f"\n[5] 创建交换机节点...")
        switch_tpl = switch_templates[0]
        switch_props = switch_tpl.get("properties", {})
        
        switch_data = {
            "name": "Switch1",
            "template_id": switch_tpl["template_id"],
            "node_type": switch_tpl.get("template_type", "ethernet_switch"),
            "compute_id": switch_tpl.get("compute_id", "local"),
            "symbol": switch_tpl.get("symbol", ":/symbols/ethernet_switch.svg"),
            "properties": {
                "console_type": switch_props.get("console_type", "telnet"),
                "platform": switch_props.get("platform", "c3745"),
                "image" : switch_props.get("image", "c3745-adventerprisek9-mz.124-15.T14.image"),
                "ram" : 256,
                # "slot0": switch_props.get("slot0", "NM-16ESW"),
                # "slot1": switch_props.get("slot1", "NM-4T"),
            },
            "x": 300,
            "y": 100,
        }
        
        print(f"发送数据: {json.dumps(switch_data)}")
        
        switch_url = f"{GNS3_SERVER}/projects/{project_id}/nodes"
        print(f"使用交换机 API: {switch_url}")
        
        r = requests.post(switch_url, json=switch_data)
        if r.status_code != 201:
            print(f"❌ 创建交换机节点失败: {r.status_code}")
            print(f"错误详情: {r.text}")
            cleanup_on_failure()
            exit(1)
        else:
            switch_node = r.json()
            switch_id = switch_node["node_id"]
            print(f"✅ Switch1 创建成功: {switch_id}")

    print("\n" + "=" * 50)
    print("✅ 拓扑创建完成!")
    print(f"项目: {project_name}")
    print(f"项目ID: {project_id}")
    print("=" * 50)

except Exception as e:
    print(f"❌ 发生错误: {e}")
    cleanup_on_failure()
    exit(1)
