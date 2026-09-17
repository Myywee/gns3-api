"""Build and configure a GNS3 project from a declarative topology file."""

from __future__ import annotations

import argparse
import json
import shlex
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from utils import RouterConfigError, config_raw, config_router, config_vpcs_commands

DEFAULT_GNS3_SERVER = "http://127.0.0.1:3080/v2"
SUPPORTED_CONFIG_DRIVERS = {"docker_start", "ios", "vpcs", "raw"}
STOPPABLE_NODE_TYPES = {
    "docker",
    "dynamips",
    "iou",
    "qemu",
    "traceng",
    "virtualbox",
    "vmware",
    "vpcs",
}


class TopologyError(ValueError):
    """Raised when a topology document is invalid."""


class GNS3APIError(RuntimeError):
    """Raised when the GNS3 API returns an unexpected response."""


def _require_mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TopologyError(f"{field} 必须是 JSON 对象")
    return value


def _require_non_empty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TopologyError(f"{field} 必须是非空字符串")
    return value.strip()


def _require_port_number(value: Any, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise TopologyError(f"{field} 必须是大于等于 0 的整数")
    return value


def load_topology(topology_path: str | Path) -> tuple[Path, dict[str, Any]]:
    path = Path(topology_path).resolve()
    try:
        with path.open("r", encoding="utf-8") as file:
            topology = json.load(file)
    except FileNotFoundError as exc:
        raise TopologyError(f"拓扑文件不存在: {path}") from exc
    except json.JSONDecodeError as exc:
        raise TopologyError(
            f"拓扑 JSON 格式错误: {path}:{exc.lineno}:{exc.colno}: {exc.msg}"
        ) from exc

    validate_topology(topology, path.parent)
    return path, topology


def validate_topology(topology: Any, base_dir: Path) -> None:
    """Validate topology structure and all local config file references."""
    root = _require_mapping(topology, "topology")
    version = root.get("version")
    if version != 1:
        raise TopologyError(f"version 仅支持 1，当前值为 {version!r}")

    project = _require_mapping(root.get("project"), "project")
    _require_non_empty_string(project.get("name"), "project.name")
    if "auto_start" in project and not isinstance(project["auto_start"], bool):
        raise TopologyError("project.auto_start 必须是布尔值")
    if "stop_after_build" in project and not isinstance(
        project["stop_after_build"], bool
    ):
        raise TopologyError("project.stop_after_build 必须是布尔值")

    templates = _require_mapping(root.get("templates"), "templates")
    if not templates:
        raise TopologyError("templates 不能为空")
    for alias, template in templates.items():
        _require_non_empty_string(alias, "templates 的别名")
        spec = _require_mapping(template, f"templates.{alias}")
        if not spec.get("name") and not spec.get("template_id"):
            raise TopologyError(f"templates.{alias} 至少需要 name 或 template_id 之一")
        if spec.get("name") is not None:
            _require_non_empty_string(spec["name"], f"templates.{alias}.name")
        if spec.get("template_id") is not None:
            _require_non_empty_string(
                spec["template_id"], f"templates.{alias}.template_id"
            )

    nodes = root.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        raise TopologyError("nodes 必须是非空数组")

    node_names: set[str] = set()
    for index, node in enumerate(nodes):
        prefix = f"nodes[{index}]"
        spec = _require_mapping(node, prefix)
        name = _require_non_empty_string(spec.get("name"), f"{prefix}.name")
        if name in node_names:
            raise TopologyError(f"节点名称重复: {name}")
        node_names.add(name)

        template_alias = _require_non_empty_string(
            spec.get("template"), f"{prefix}.template"
        )
        if template_alias not in templates:
            raise TopologyError(f"节点 {name} 引用了不存在的模板别名: {template_alias}")

        position = _require_mapping(spec.get("position"), f"{prefix}.position")
        for coordinate in ("x", "y"):
            value = position.get(coordinate)
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise TopologyError(f"{prefix}.position.{coordinate} 必须是数字")

        if "config" in spec:
            config = _require_mapping(spec["config"], f"{prefix}.config")
            driver = _require_non_empty_string(
                config.get("driver"), f"{prefix}.config.driver"
            )
            if driver not in SUPPORTED_CONFIG_DRIVERS:
                supported = ", ".join(sorted(SUPPORTED_CONFIG_DRIVERS))
                raise TopologyError(
                    f"{prefix}.config.driver 不支持 {driver!r}，可选值: {supported}"
                )
            has_file = "file" in config
            has_commands = "commands" in config
            if has_file == has_commands:
                raise TopologyError(
                    f"{prefix}.config 必须且只能包含 file 或 commands 之一"
                )
            if has_file:
                config_file = _require_non_empty_string(
                    config["file"], f"{prefix}.config.file"
                )
                resolved = (base_dir / config_file).resolve()
                if not resolved.is_file():
                    raise TopologyError(f"节点 {name} 的配置文件不存在: {resolved}")
                _read_commands(config, base_dir)
            else:
                commands = config["commands"]
                if not isinstance(commands, list) or not commands:
                    raise TopologyError(f"{prefix}.config.commands 必须是非空数组")
                for command_index, command in enumerate(commands):
                    _require_non_empty_string(
                        command, f"{prefix}.config.commands[{command_index}]"
                    )

    links = root.get("links")
    if not isinstance(links, list):
        raise TopologyError("links 必须是数组")

    used_endpoints: set[tuple[str, int, int]] = set()
    for link_index, link in enumerate(links):
        prefix = f"links[{link_index}]"
        link_spec = _require_mapping(link, prefix)
        endpoints = link_spec.get("endpoints")
        if not isinstance(endpoints, list) or len(endpoints) != 2:
            raise TopologyError(f"{prefix}.endpoints 必须恰好包含两个端点")
        for endpoint_index, endpoint in enumerate(endpoints):
            endpoint_prefix = f"{prefix}.endpoints[{endpoint_index}]"
            endpoint_spec = _require_mapping(endpoint, endpoint_prefix)
            node_name = _require_non_empty_string(
                endpoint_spec.get("node"), f"{endpoint_prefix}.node"
            )
            if node_name not in node_names:
                raise TopologyError(
                    f"{endpoint_prefix} 引用了不存在的节点: {node_name}"
                )
            adapter = _require_port_number(
                endpoint_spec.get("adapter"), f"{endpoint_prefix}.adapter"
            )
            port = _require_port_number(
                endpoint_spec.get("port"), f"{endpoint_prefix}.port"
            )
            endpoint_key = (node_name, adapter, port)
            if endpoint_key in used_endpoints:
                raise TopologyError(
                    f"端口被重复连接: {node_name} adapter={adapter} port={port}"
                )
            used_endpoints.add(endpoint_key)


def _read_commands(config: dict[str, Any], base_dir: Path) -> list[str]:
    if "commands" in config:
        return [command.strip() for command in config["commands"]]

    config_path = (base_dir / config["file"]).resolve()
    commands: list[str] = []
    with config_path.open("r", encoding="utf-8") as file:
        for line in file:
            command = line.strip()
            if command and not command.startswith("#"):
                commands.append(command)
    if not commands:
        raise TopologyError(f"配置文件没有可执行命令: {config_path}")
    return commands


class GNS3Client:
    def __init__(
        self,
        server: str = DEFAULT_GNS3_SERVER,
        session: requests.Session | None = None,
        timeout: int = 30,
    ) -> None:
        self.server = server.rstrip("/")
        self.session = session or requests.Session()
        self.timeout = timeout

    def _request(
        self,
        method: str,
        path: str,
        *,
        expected: tuple[int, ...],
        payload: dict[str, Any] | None = None,
    ) -> requests.Response:
        try:
            response = self.session.request(
                method,
                f"{self.server}{path}",
                json=payload,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise GNS3APIError(f"无法连接 GNS3 服务 {self.server}: {exc}") from exc
        if response.status_code not in expected:
            details = response.text.strip()
            raise GNS3APIError(
                f"GNS3 API {method} {path} 返回 {response.status_code}: {details}"
            )
        return response

    def list_templates(self) -> list[dict[str, Any]]:
        return self._request("GET", "/templates", expected=(200,)).json()

    def create_project(self, name: str) -> dict[str, Any]:
        return self._request(
            "POST", "/projects", expected=(201,), payload={"name": name}
        ).json()

    def delete_project(self, project_id: str) -> None:
        try:
            self._request(
                "POST",
                f"/projects/{project_id}/stop",
                expected=(200, 204, 404, 409),
            )
            self._request("DELETE", f"/projects/{project_id}", expected=(204, 404))
        except GNS3APIError as exc:
            print(f"[WARN] 自动清理项目失败: {exc}")

    def create_node_from_template(
        self,
        project_id: str,
        template_id: str,
        node: dict[str, Any],
        compute_id: str | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": node["name"],
            "x": node["position"]["x"],
            "y": node["position"]["y"],
        }
        if compute_id:
            payload["compute_id"] = compute_id
        return self._request(
            "POST",
            f"/projects/{project_id}/templates/{template_id}",
            expected=(201,),
            payload=payload,
        ).json()

    def create_link(
        self,
        project_id: str,
        link: dict[str, Any],
        nodes_by_name: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        endpoints = []
        for endpoint in link["endpoints"]:
            endpoints.append(
                {
                    "node_id": nodes_by_name[endpoint["node"]]["node_id"],
                    "adapter_number": endpoint["adapter"],
                    "port_number": endpoint["port"],
                }
            )
        return self._request(
            "POST",
            f"/projects/{project_id}/links",
            expected=(201,),
            payload={"nodes": endpoints},
        ).json()

    def update_node_properties(
        self,
        project_id: str,
        node_id: str,
        properties: dict[str, Any],
    ) -> dict[str, Any]:
        return self._request(
            "PUT",
            f"/projects/{project_id}/nodes/{node_id}",
            expected=(200,),
            payload={"properties": properties},
        ).json()

    def start_node(self, project_id: str, node_id: str) -> None:
        self._request(
            "POST",
            f"/projects/{project_id}/nodes/{node_id}/start",
            expected=(200, 409),
        )

    def stop_node(self, project_id: str, node_id: str) -> None:
        self._request(
            "POST",
            f"/projects/{project_id}/nodes/{node_id}/stop",
            expected=(200, 204, 409),
        )


def _resolve_templates(
    topology: dict[str, Any], available: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    by_id = {template.get("template_id"): template for template in available}
    by_name: dict[str, list[dict[str, Any]]] = {}
    for template in available:
        by_name.setdefault(template.get("name", ""), []).append(template)

    resolved: dict[str, dict[str, Any]] = {}
    for alias, spec in topology["templates"].items():
        template = None
        if spec.get("template_id"):
            template = by_id.get(spec["template_id"])
        if template is None and spec.get("name"):
            matches = by_name.get(spec["name"], [])
            if len(matches) > 1:
                raise TopologyError(
                    f"模板名称 {spec['name']!r} 不唯一，请在 topology.json 中指定 template_id"
                )
            if matches:
                template = matches[0]
        if template is None:
            identity = spec.get("template_id") or spec.get("name")
            raise TopologyError(f"GNS3 中找不到模板 {alias}: {identity}")
        resolved[alias] = template
    return resolved


def _runtime_node(node: dict[str, Any]) -> dict[str, Any]:
    return {
        key: node.get(key)
        for key in (
            "node_id",
            "name",
            "node_type",
            "console",
            "console_host",
            "console_type",
            "compute_id",
        )
    }


def _write_state(state_path: Path, state: dict[str, Any]) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    with state_path.open("w", encoding="utf-8") as file:
        json.dump(state, file, ensure_ascii=False, indent=2)
        file.write("\n")


def _docker_start_command(commands: list[str]) -> str:
    script = "; ".join(["set -e", *commands, "exec /bin/bash"])
    return f"/bin/bash -lc {shlex.quote(script)}"


def configure_docker_start_commands(
    client: GNS3Client,
    project_id: str,
    topology: dict[str, Any],
    topology_dir: Path,
    nodes_by_name: dict[str, dict[str, Any]],
    *,
    restart: bool = False,
) -> None:
    docker_nodes = [
        node
        for node in topology["nodes"]
        if node.get("config", {}).get("driver") == "docker_start"
    ]
    if not docker_nodes:
        return

    print("\n开始写入 Docker Start command...")
    for node_spec in docker_nodes:
        name = node_spec["name"]
        runtime = nodes_by_name.get(name)
        if runtime is None:
            raise TopologyError(f"运行状态中缺少节点: {name}")
        if runtime.get("node_type") != "docker":
            raise TopologyError(
                f"节点 {name} 使用 docker_start 驱动，但实际类型不是 docker"
            )

        commands = _read_commands(node_spec["config"], topology_dir)
        start_command = _docker_start_command(commands)
        if restart:
            client.stop_node(project_id, runtime["node_id"])
        updated = client.update_node_properties(
            project_id,
            runtime["node_id"],
            {"start_command": start_command},
        )
        nodes_by_name[name] = {**runtime, **updated}
        if restart:
            client.start_node(project_id, runtime["node_id"])
        action = "已更新并重启" if restart else "已写入"
        print(f"  [OK] {name}: {action}，{len(commands)} 条命令")
    print("[OK] Docker Start command 已应用")


def configure_nodes(
    topology: dict[str, Any],
    topology_dir: Path,
    nodes_by_name: dict[str, dict[str, Any]],
) -> None:
    configurable_nodes = [
        node
        for node in topology["nodes"]
        if node.get("config")
        and node["config"].get("driver") != "docker_start"
    ]
    if not configurable_nodes:
        return

    print("\n开始应用设备配置...")
    for node_spec in configurable_nodes:
        name = node_spec["name"]
        runtime = nodes_by_name.get(name)
        if runtime is None:
            raise TopologyError(f"运行状态中缺少节点: {name}")
        console = runtime.get("console")
        if console is None:
            raise TopologyError(f"节点 {name} 没有可用的 console 端口")
        host = runtime.get("console_host") or "127.0.0.1"
        config = node_spec["config"]
        commands = _read_commands(config, topology_dir)
        driver = config["driver"]
        print(f"  - {name}: {driver}, {len(commands)} 条命令")
        if driver == "ios":
            config_router(console, commands, host=host)
        elif driver == "vpcs":
            config_vpcs_commands(console, commands, host=host)
        else:
            config_raw(console, commands, host=host)
    print("[OK] 所有设备配置已应用")


def stop_nodes(
    client: GNS3Client,
    project_id: str,
    nodes_by_name: dict[str, dict[str, Any]],
) -> tuple[list[str], list[str]]:
    stopped: list[str] = []
    always_running: list[str] = []
    print("\n开始关闭节点...")
    for name, node in reversed(list(nodes_by_name.items())):
        if node.get("node_type") not in STOPPABLE_NODE_TYPES:
            always_running.append(name)
            print(f"  [SKIP] 常驻节点无需关闭: {name}")
            continue
        client.stop_node(project_id, node["node_id"])
        stopped.append(name)
        print(f"  [OK] 已关闭: {name}")
    print("[OK] 所有可关机节点均已关闭")
    return stopped, always_running


def build_topology(
    topology_path: str | Path,
    *,
    server: str = DEFAULT_GNS3_SERVER,
    state_path: str | Path | None = None,
    apply_config: bool = True,
) -> dict[str, Any]:
    topology_file, topology = load_topology(topology_path)
    topology_dir = topology_file.parent
    runtime_path = (
        Path(state_path).resolve()
        if state_path is not None
        else topology_dir / "build_state.json"
    )
    client = GNS3Client(server)

    resolved_templates = _resolve_templates(topology, client.list_templates())
    project = client.create_project(topology["project"]["name"])
    project_id = project["project_id"]
    nodes_by_name: dict[str, dict[str, Any]] = {}
    links: list[dict[str, Any]] = []
    print(f"[OK] 项目已创建: {topology['project']['name']} ({project_id})")

    try:
        for node_spec in topology["nodes"]:
            template_spec = topology["templates"][node_spec["template"]]
            template = resolved_templates[node_spec["template"]]
            compute_id = node_spec.get("compute_id") or template_spec.get("compute_id")
            node = client.create_node_from_template(
                project_id, template["template_id"], node_spec, compute_id
            )
            nodes_by_name[node_spec["name"]] = node
            print(f"  [OK] 节点: {node_spec['name']} <- {template['name']}")

        if apply_config:
            configure_docker_start_commands(
                client,
                project_id,
                topology,
                topology_dir,
                nodes_by_name,
            )

        for link_spec in topology["links"]:
            link = client.create_link(project_id, link_spec, nodes_by_name)
            links.append(link)
            left, right = link_spec["endpoints"]
            print(
                "  [OK] 链路: "
                f"{left['node']}[{left['adapter']}/{left['port']}] <-> "
                f"{right['node']}[{right['adapter']}/{right['port']}]"
            )

        if topology["project"].get("auto_start", True):
            print("\n开始启动节点...")
            for name, node in nodes_by_name.items():
                client.start_node(project_id, node["node_id"])
                print(f"  [OK] 已启动: {name}")
    except Exception:
        client.delete_project(project_id)
        raise

    state = {
        "schema_version": 1,
        "topology_file": topology_file.name,
        "project_id": project_id,
        "project_name": topology["project"]["name"],
        "server": server,
        "built_at": datetime.now(timezone.utc).isoformat(),
        "nodes": {name: _runtime_node(node) for name, node in nodes_by_name.items()},
        "link_ids": [link.get("link_id") for link in links],
        "configured": False,
    }
    _write_state(runtime_path, state)
    print(f"[OK] 运行状态已写入: {runtime_path}")

    configuration_failure = None
    if apply_config:
        try:
            configure_nodes(topology, topology_dir, nodes_by_name)
        except Exception as exc:
            configuration_failure = exc
            state["configuration_error"] = str(exc)
            state["configuration_failed_at"] = datetime.now(timezone.utc).isoformat()
            print("[WARN] 配置失败；项目已保留，可修正后使用 configure 子命令重试")
        else:
            state["configured"] = True
            state["configured_at"] = datetime.now(timezone.utc).isoformat()
            _write_state(runtime_path, state)

    if topology["project"].get("stop_after_build", True):
        try:
            stopped, always_running = stop_nodes(
                client,
                project_id,
                nodes_by_name,
            )
        except Exception:
            print("[WARN] 节点关闭失败；项目已保留，请在 GNS3 中检查节点状态")
            raise
        state["nodes_stopped"] = True
        state["stopped_at"] = datetime.now(timezone.utc).isoformat()
        state["stopped_nodes"] = stopped
        state["always_running_nodes"] = always_running
        _write_state(runtime_path, state)

    if configuration_failure is not None:
        raise configuration_failure
    return state


def configure_existing(
    topology_path: str | Path,
    *,
    state_path: str | Path | None = None,
) -> dict[str, Any]:
    topology_file, topology = load_topology(topology_path)
    runtime_path = (
        Path(state_path).resolve()
        if state_path is not None
        else topology_file.parent / "build_state.json"
    )
    try:
        with runtime_path.open("r", encoding="utf-8") as file:
            state = json.load(file)
    except FileNotFoundError as exc:
        raise TopologyError(f"运行状态文件不存在: {runtime_path}") from exc

    project_id = _require_non_empty_string(
        state.get("project_id"), "build_state.project_id"
    )
    server = state.get("server") or DEFAULT_GNS3_SERVER
    _require_non_empty_string(server, "build_state.server")
    nodes = _require_mapping(state.get("nodes"), "build_state.nodes")
    client = GNS3Client(server)
    state["configured"] = False
    state.pop("configured_at", None)
    state.pop("configuration_error", None)
    state["configuration_started_at"] = datetime.now(timezone.utc).isoformat()
    _write_state(runtime_path, state)

    failure = None
    try:
        configure_docker_start_commands(
            client,
            project_id,
            topology,
            topology_file.parent,
            nodes,
            restart=True,
        )

        # A successful build normally leaves IOS nodes powered off.  Start the
        # non-Docker configurable nodes before opening their consoles.  Starting
        # an already-running GNS3 node is harmless (the API may return 409).
        for node_spec in topology["nodes"]:
            config = node_spec.get("config")
            if not config or config.get("driver") == "docker_start":
                continue
            runtime = nodes[node_spec["name"]]
            if runtime.get("node_type") in STOPPABLE_NODE_TYPES:
                client.start_node(project_id, runtime["node_id"])
                print(f"  [OK] 已启动待配置节点: {node_spec['name']}")

        configure_nodes(topology, topology_file.parent, nodes)
        state["configured"] = True
        state["configured_at"] = datetime.now(timezone.utc).isoformat()
    except Exception as exc:
        failure = exc
        state["configuration_error"] = str(exc)
        state["configuration_failed_at"] = datetime.now(timezone.utc).isoformat()
    finally:
        state["nodes"] = {
            name: _runtime_node(node) for name, node in nodes.items()
        }
        if topology["project"].get("stop_after_build", True):
            stopped, always_running = stop_nodes(client, project_id, nodes)
            state["nodes_stopped"] = True
            state["stopped_at"] = datetime.now(timezone.utc).isoformat()
            state["stopped_nodes"] = stopped
            state["always_running_nodes"] = always_running
        _write_state(runtime_path, state)

    if failure is not None:
        raise failure
    return state


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="根据声明式 JSON 创建并配置 GNS3 拓扑")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate", help="离线校验拓扑和配置文件")
    validate_parser.add_argument("topology", help="topology.json 路径")

    build_parser = subparsers.add_parser("build", help="创建、连接、启动并配置拓扑")
    build_parser.add_argument("topology", help="topology.json 路径")
    build_parser.add_argument("--server", default=DEFAULT_GNS3_SERVER)
    build_parser.add_argument("--state", help="运行状态输出路径")
    build_parser.add_argument(
        "--no-config", action="store_true", help="只创建拓扑，暂不应用配置"
    )

    configure_parser = subparsers.add_parser(
        "configure", help="根据 build_state.json 重新应用配置"
    )
    configure_parser.add_argument("topology", help="topology.json 路径")
    configure_parser.add_argument("--state", help="运行状态文件路径")
    return parser


def main(argv: list[str] | None = None) -> int:
    # Windows Python may still default to GBK even in a UTF-8 capable terminal.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "validate":
            path, _ = load_topology(args.topology)
            print(f"[OK] 拓扑定义校验通过: {path}")
        elif args.command == "build":
            build_topology(
                args.topology,
                server=args.server,
                state_path=args.state,
                apply_config=not args.no_config,
            )
        else:
            configure_existing(args.topology, state_path=args.state)
    except (TopologyError, GNS3APIError, RouterConfigError, OSError) as exc:
        print(f"[ERROR] {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
