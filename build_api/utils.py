import json
import re
import requests
import telnetlib
import time

GNS3_SERVER = "http://127.0.0.1:3080/v2"
ROUTER_INITIALIZATION_TIMEOUT = 600
ROUTER_CONSOLE_POLL_TIMEOUT = 5
ROUTER_COMMAND_TIMEOUT = 30
ROUTER_SAVE_TIMEOUT = 120
ROUTER_CONNECT_RETRY_INTERVAL = 2

IOS_USER_PROMPT = re.compile(rb"(?m)^[^\r\n()]+>\s*$")
IOS_PRIVILEGED_PROMPT = re.compile(rb"(?m)^[^\r\n()]+#\s*$")
IOS_CONFIG_PROMPT = re.compile(rb"(?m)^[^\r\n]+\(config[^)]*\)#\s*$")
IOS_DESTINATION_PROMPT = re.compile(rb"Destination filename \[[^]]+\]\?")
IOS_ERROR_PATTERNS = (
    "% Invalid input",
    "% Incomplete command",
    "% Ambiguous command",
    "% Authorization failed",
    "% Bad IP address",
    "% Configuration failed",
    "% Error",
)


class RouterConfigError(RuntimeError):
    """Raised when IOS does not accept, save, or verify a router configuration."""

def  cleanup_on_failure(project_id):
    if project_id:
        try:
            r = requests.get(f"{GNS3_SERVER}/projects/{project_id}")
            if r.status_code == 200:
                proj = r.json()
                if proj.get('status') == 'started':
                    requests.post(f"{GNS3_SERVER}/projects/{project_id}/stop")
                requests.delete(f"{GNS3_SERVER}/projects/{project_id}")
                print(f"✅ 已清理项目")
        except Exception as e:
            print(f"⚠️  清理失败: {e}")

def get_templates():
    try:
        r = requests.get(f"{GNS3_SERVER}/templates")
        if r.status_code != 200:
            print(f"❌ 获取模板失败: {r.status_code}")
            exit(1)
        return r.json()
    except requests.exceptions.ConnectionError:
        print("❌ 连接错误: 请检查 GNS3 服务器是否运行")
        exit(1)

def find_template(templates, template_name):
    for tpl in templates:
        if tpl["name"] == template_name:
            return tpl
    return None

def create_project(project_name):
    try:
        r = requests.post(f"{GNS3_SERVER}/projects", json={"name": project_name})
        if r.status_code != 201:
            print(f"❌ 创建项目失败: {r.status_code}")
            exit(1)
        return r.json()["project_id"]
    except requests.exceptions.ConnectionError:
        print("❌ 连接错误: 请检查 GNS3 服务器是否运行")
        exit(1)

def create_vpcs(project_id, name, tpl, x, y, compute_id = 'vm'):
    try:
        data = {
            "name": name,
            "template_id": tpl["template_id"],
            "node_type": tpl["template_type"],
            "symbol": tpl["symbol"],
            "compute_id": tpl["compute_id"] if tpl["compute_id"] else compute_id,
            "properties": tpl["properties"],
            "x": x,
            "y": y
     }
        r = requests.post(f"{GNS3_SERVER}/projects/{project_id}/nodes", json=data)
        if r.status_code != 201:
            print(f"❌ 创建节点失败: {r.status_code}")
            cleanup_on_failure(project_id)
            exit(1)
        return r.json()
    except requests.exceptions.ConnectionError:
        print("❌ 连接错误: 请检查 GNS3 服务器是否运行")
        cleanup_on_failure(project_id)
        exit(1)

def create_qemu(project_id, name, tpl, x, y, compute_id = 'vm'):
    try:
        data = {
        "name" : name,
        "template_id": tpl["template_id"],
        "node_type": tpl["template_type"],
        "compute_id": tpl["compute_id"] if tpl["compute_id"] else compute_id,
        "symbol" : tpl["symbol"],
        "properties" : {
            "qemu_path": tpl["qemu_path"],
            "console_type": tpl["console_type"]
        },
        "x": x,
        "y": y
    }
        r = requests.post(f"{GNS3_SERVER}/projects/{project_id}/nodes", json=data)
        if r.status_code != 201:
            print(f"❌ 创建节点失败: {r.status_code}")
            cleanup_on_failure(project_id)
            exit(1)
        return r.json()
    except requests.exceptions.ConnectionError:
        print("❌ 连接错误: 请检查 GNS3 服务器是否运行")
        cleanup_on_failure(project_id)
        exit(1)
        
def create_docker(project_id, name, tpl, x, y, compute_id = 'vm'):
    try:
        data = {
        "name": name,
        "template_id": tpl["template_id"],
        "node_type": tpl["template_type"],
        "compute_id": tpl["compute_id"] if tpl["compute_id"] else compute_id,
        "symbol": tpl["symbol"],
        "properties": {
            "image" : tpl["image"],
            "console_type": tpl["console_type"]
        },
        "x": x,
        "y": y
    }

        r = requests.post(f"{GNS3_SERVER}/projects/{project_id}/nodes", json=data)
        if r.status_code != 201:
            print(f"❌ 创建节点失败: {r.status_code}")
            cleanup_on_failure(project_id)
            exit(1)
        return r.json()
    except requests.exceptions.ConnectionError:
        print("❌ 连接错误: 请检查 GNS3 服务器是否运行")
        cleanup_on_failure(project_id)
        exit(1)
        

def create_router(project_id, name, tpl, x, y, compute_id = 'vm'):
    try:
        data = {
        "name": name,
        "template_id": tpl["template_id"],
        "node_type": tpl["template_type"],
        "compute_id": tpl["compute_id"] if tpl["compute_id"] else compute_id,
        "symbol": tpl["symbol"],
        "properties": {
            "image" : tpl["image"],
            "console_type": tpl["console_type"],
            "platform" : tpl["platform"],
            "ram" : tpl["ram"],
            "slot0": tpl["slot0"],
            "slot1": tpl["slot1"],
            "slot2": tpl["slot2"],
            "slot3": tpl["slot3"],
            "slot4": tpl["slot4"],
            "wic0": tpl["wic0"],
            "wic1": tpl["wic1"],
            "wic2": tpl["wic2"]
        },
        "x": x,
        "y": y
    }
        r = requests.post(f"{GNS3_SERVER}/projects/{project_id}/nodes", json=data)
        if r.status_code != 201:
            print(f"❌ 创建节点失败: {r.status_code}")
            cleanup_on_failure(project_id)
            exit(1)
        return r.json()
    except requests.exceptions.ConnectionError:
        print("❌ 连接错误: 请检查 GNS3 服务器是否运行")
        cleanup_on_failure(project_id)
        exit(1)


def create_switch(project_id, name, tpl, x, y, compute_id = 'vm'):
    try:
        data = {
        "name": name,
        "template_id": tpl["template_id"],
        "node_type": tpl["template_type"],
        "compute_id": tpl["compute_id"] if tpl["compute_id"] else compute_id,
        "symbol": tpl["symbol"],
        "properties": {
            "image" : tpl["image"],
            "console_type": tpl["console_type"],
            "platform" : tpl["platform"],
            "ram" : tpl["ram"]
        },
        "x": x,
        "y": y
    }

        r = requests.post(f"{GNS3_SERVER}/projects/{project_id}/nodes", json=data)
        if r.status_code != 201:
            print(f"❌ 创建节点失败: {r.status_code}")
            cleanup_on_failure(project_id)
            exit(1)
        return r.json()
    except requests.exceptions.ConnectionError:
        print("❌ 连接错误: 请检查 GNS3 服务器是否运行")
        cleanup_on_failure(project_id)
        exit(1)

def connect(project_id, node1, adapter1,port1, node2, adapter2, port2):
    try:
        data = {
        "nodes": [
            {"node_id": node1["node_id"], "adapter_number": adapter1, "port_number": port1},
            {"node_id": node2["node_id"], "adapter_number": adapter2, "port_number": port2}
        ]
    }
        r = requests.post(f"{GNS3_SERVER}/projects/{project_id}/links", json=data)
        if r.status_code != 201:
            print(f"❌ 连接节点失败: {node1['name']} {port1} -> {node2['name']} {port2}, {r.status_code}")
            print(f"错误详情: {r.text}")
            cleanup_on_failure(project_id)
            exit(1)
        return r.json()
    except requests.exceptions.ConnectionError:
        print("❌ 连接错误: 请检查 GNS3 服务器是否运行")
        cleanup_on_failure(project_id)
        exit(1)

def start_node(project_id, node):
    try:
        r = requests.post(f"{GNS3_SERVER}/projects/{project_id}/nodes/{node['node_id']}/start")
        if r.status_code != 200:
            print(f"❌ 启动节点失败: {node['name']}, {r.status_code}")
            return False
        print(f"✅ 节点已启动: {node['name']}")
        return True
    except requests.exceptions.ConnectionError:
        print(f"❌ 连接错误: 请检查 GNS3 服务器是否运行")
        return False

def start_all_nodes(project_id, nodes):
    print("\n开始启动所有节点...")
    for node in nodes:
        start_node(project_id, node)
        time.sleep(1)
    print("✅ 所有节点启动完成\n")


GNS_VM = "192.168.127.131"

def router_initialize(
    tn,
    timeout=ROUTER_INITIALIZATION_TIMEOUT,
    poll_timeout=ROUTER_CONSOLE_POLL_TIMEOUT,
):
    deadline = time.monotonic() + timeout
    attempt = 0
    while time.monotonic() < deadline:
        attempt += 1
        try:
            remaining = deadline - time.monotonic()
            idx, matched, output = tn.expect([
                b"initial configuration dialog",
                b"Press RETURN to get started",
                IOS_USER_PROMPT,
                IOS_PRIVILEGED_PROMPT,
                b"Password:",
                b"--More--",
                b"Switch>",
                b"Switch#",
                b"Would you like to terminate autoinstall?"
            ], timeout=max(0.1, min(poll_timeout, remaining)))

            console_output = output.decode('utf-8', errors='ignore') if output else ""
            if console_output:
                print(f"[DEBUG] Attempt {attempt}: console output:\n{console_output}")

            if idx == 0:
                tn.write(b"no\r\n")
                time.sleep(0.5)
            elif idx == 1:
                tn.write(b"\r\n")
                time.sleep(0.5)
            elif idx == 2:
                tn.write(b"enable\r\n")
                time.sleep(0.5)
            elif idx == 3:
                return True
            elif idx == 4:
                tn.write(b"\r\n")
                time.sleep(0.5)
            elif idx == 5:
                tn.write(b" \r\n")
                time.sleep(0.5)
            elif idx == 6:
                tn.write(b"enable\r\n")
                time.sleep(0.5)
            elif idx == 7:
                return True
            elif idx == 8:
                tn.write(b"yes\r\n")
                time.sleep(0.5)
            else:
                time.sleep(0.5)
        except Exception as e:
            print(f"[DEBUG] Attempt {attempt}: exception: {e}")
            time.sleep(0.5)
    return False

def config_raw(port, commands, host=GNS_VM, line_ending="\n"):
    tn = telnetlib.Telnet(host, port)
    time.sleep(1)
    try:
        for command in commands:
            tn.write(command.encode() + line_ending.encode())
            time.sleep(0.5)
    finally:
        tn.close()


def config_vpcs_commands(port, commands, host=GNS_VM):
    config_raw(port, commands, host=host, line_ending="\n")


def config_vpcs(port, ip, gw, host=GNS_VM):
    config_vpcs_commands(port, [f"ip {ip} {gw}", "save"], host=host)


def _decode_console_output(output):
    return output.decode("utf-8", errors="ignore") if output else ""


def _raise_for_ios_errors(output, command):
    text = _decode_console_output(output)
    for pattern in IOS_ERROR_PATTERNS:
        if pattern.lower() in text.lower():
            raise RouterConfigError(
                f"IOS 拒绝命令 {command!r}: {text.strip()}"
            )


def _send_ios_command(tn, command, prompt, timeout=ROUTER_COMMAND_TIMEOUT):
    tn.write(command.encode() + b"\r\n")
    index, _, output = tn.expect([prompt], timeout=timeout)
    if index < 0:
        text = _decode_console_output(output).strip()
        raise RouterConfigError(
            f"等待命令 {command!r} 的 IOS 提示符超时；最后输出: {text!r}"
        )
    _raise_for_ios_errors(output, command)
    return output


def _save_ios_config(tn):
    command = "copy running-config startup-config"
    tn.write(command.encode() + b"\r\n")
    index, _, output = tn.expect(
        [IOS_DESTINATION_PROMPT, IOS_PRIVILEGED_PROMPT],
        timeout=ROUTER_SAVE_TIMEOUT,
    )
    if index < 0:
        raise RouterConfigError("等待 startup-config 文件名确认时超时")

    transcript = output
    if index == 0:
        tn.write(b"\r\n")
        index, _, output = tn.expect(
            [IOS_PRIVILEGED_PROMPT],
            timeout=ROUTER_SAVE_TIMEOUT,
        )
        transcript += output
        if index < 0:
            raise RouterConfigError("等待 IOS 保存 startup-config 完成时超时")

    _raise_for_ios_errors(transcript, command)


def _connect_router_console(host, port, timeout=ROUTER_INITIALIZATION_TIMEOUT):
    deadline = time.monotonic() + timeout
    last_error = None
    while time.monotonic() < deadline:
        try:
            return telnetlib.Telnet(host, port, timeout=ROUTER_COMMAND_TIMEOUT)
        except OSError as exc:
            last_error = exc
            time.sleep(ROUTER_CONNECT_RETRY_INTERVAL)
    raise RouterConfigError(
        f"等待路由器 Console {host}:{port} 可连接超时: {last_error}"
    )


def config_router(port, commands, host=GNS_VM):
    tn = _connect_router_console(host, port)
    time.sleep(1)
    try:
        if not router_initialize(tn):
            raise RouterConfigError("等待 IOS 特权模式提示符超时，未下发配置")

        _send_ios_command(tn, "terminal length 0", IOS_PRIVILEGED_PROMPT)
        _send_ios_command(tn, "configure terminal", IOS_CONFIG_PROMPT)

        for cmd in commands:
            _send_ios_command(tn, cmd, IOS_CONFIG_PROMPT)

        _send_ios_command(tn, "end", IOS_PRIVILEGED_PROMPT)
        _save_ios_config(tn)
        print("[OK] Router 配置命令已应用并执行保存")
    finally:
        tn.close()

def get_all_nodes(project_id):
    try:
        r = requests.get(f"{GNS3_SERVER}/projects/{project_id}/nodes")
        if r.status_code != 200:
            print(f"❌ 获取节点失败: {r.status_code}")
            return None
        return r.json()
    except requests.exceptions.ConnectionError:
        print("❌ 连接错误: 请检查 GNS3 服务器是否运行")
        return None

def get_links(project_id):
    try:
        r = requests.get(f"{GNS3_SERVER}/projects/{project_id}/links")
        if r.status_code != 200:
            print(f"❌ 获取链路失败: {r.status_code}")
            return None
        return r.json()
    except requests.exceptions.ConnectionError:
        print("❌ 连接错误: 请检查 GNS3 服务器是否运行")
        return None

def get_topology(project_id):
    nodes = get_all_nodes(project_id)
    links = get_links(project_id)

    if nodes is None or links is None:
        return None

    node_id_to_name = {n["node_id"]: n["name"] for n in nodes}

    topo = {
        "nodes": [],
        "links": []
    }

    for n in nodes:
        topo["nodes"].append({
            "name": n["name"],
            "type": n["node_type"],
            "x": n["x"],
            "y": n["y"]
        })

    for l in links:
        n1, n2 = l["nodes"]
        topo["links"].append({
            "source": node_id_to_name.get(n1["node_id"], n1["node_id"]),
            "target": node_id_to_name.get(n2["node_id"], n2["node_id"]),
            "src_adapter": n1["adapter_number"],
            "dst_adapter": n2["adapter_number"],
            "src_port": n1["port_number"],
            "dst_port": n2["port_number"]
        })

    return topo

