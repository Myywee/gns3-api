import copy
import json
import shlex
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_api"))

from topology_build import (  # noqa: E402
    TopologyError,
    _docker_start_command,
    _resolve_templates,
    build_topology,
    configure_docker_start_commands,
    configure_existing,
    load_topology,
    validate_topology,
)
from utils import (  # noqa: E402
    ROUTER_INITIALIZATION_TIMEOUT,
    RouterConfigError,
    config_router,
)


LAB1_TOPOLOGY_PATH = ROOT / "build_api" / "lab1-start" / "topology.json"
LAB1_COMPLETE_TOPOLOGY_PATH = (
    ROOT / "build_api" / "lab1-complete" / "topology.json"
)
LAB2_STARTER_TOPOLOGY_PATH = (
    ROOT / "build_api" / "lab2-start" / "topology.json"
)
LAB2_COMPLETE_TOPOLOGY_PATH = (
    ROOT / "build_api" / "lab2-complete" / "topology.json"
)
LAB3_START_TOPOLOGY_PATH = (
    ROOT / "build_api" / "lab3-start" / "topology.json"
)
LAB3_COMPLETE_TOPOLOGY_PATH = (
    ROOT / "build_api" / "lab3-complete" / "topology.json"
)


class FakeGNS3Client:
    instance = None

    def __init__(self, server):
        self.server = server
        self.created_nodes = []
        self.created_links = []
        self.started_nodes = []
        self.stopped_nodes = []
        self.updated_nodes = []
        self.deleted_projects = []
        self.events = []
        FakeGNS3Client.instance = self

    def list_templates(self):
        return [
            {"name": "NAT", "template_id": "nat-id"},
            {"name": "Ethernet switch", "template_id": "switch-id"},
            {"name": "Cisco IOSv", "template_id": "iosv-id"},
            {
                "name": "client-lab1-no-cache",
                "template_id": "client-lab1-id",
            },
            {
                "name": "dns-server-lab1-no-recursion",
                "template_id": "dns-lab1-id",
            },
            {
                "name": "web-server-lab1-vulnerable",
                "template_id": "web-lab1-id",
            },
        ]

    def create_project(self, name):
        return {"name": name, "project_id": "project-id"}

    def create_node_from_template(
        self, project_id, template_id, node, compute_id
    ):
        node_types = {
            "client-lab1-id": "docker",
            "dns-lab1-id": "docker",
            "web-lab1-id": "docker",
            "iosv-id": "qemu",
        }
        runtime = {
            "node_id": f"node-{node['name']}",
            "name": node["name"],
            "node_type": node_types.get(template_id, "test"),
            "console": 5000 + len(self.created_nodes),
            "console_host": "127.0.0.1",
            "console_type": "telnet",
            "compute_id": compute_id,
        }
        self.created_nodes.append((project_id, template_id, runtime))
        self.events.append(("create", runtime["node_id"]))
        return runtime

    def create_link(self, project_id, link, nodes_by_name):
        runtime = {"link_id": f"link-{len(self.created_links)}"}
        self.created_links.append((project_id, link, nodes_by_name))
        self.events.append(("link", runtime["link_id"]))
        return runtime

    def update_node_properties(self, project_id, node_id, properties):
        self.updated_nodes.append((project_id, node_id, properties))
        self.events.append(("update", node_id))
        runtime = next(
            runtime
            for _, _, runtime in self.created_nodes
            if runtime["node_id"] == node_id
        )
        return {**runtime, "properties": properties}

    def start_node(self, project_id, node_id):
        self.started_nodes.append((project_id, node_id))
        self.events.append(("start", node_id))

    def stop_node(self, project_id, node_id):
        self.stopped_nodes.append((project_id, node_id))
        self.events.append(("stop", node_id))

    def delete_project(self, project_id):
        self.deleted_projects.append(project_id)


class ScriptedTelnet:
    """Minimal Telnet double that returns an IOS transcript one prompt at a time."""

    def __init__(self, responses):
        self.responses = iter(responses)
        self.writes = []
        self.closed = False

    def expect(self, patterns, timeout=None):
        del patterns, timeout
        return next(self.responses)

    def write(self, data):
        self.writes.append(data)

    def close(self):
        self.closed = True


class TopologyValidationTests(unittest.TestCase):
    def test_lab3_complete_uses_requested_complete_web_template(self):
        _, topology = load_topology(LAB3_COMPLETE_TOPOLOGY_PATH)
        nodes = {node["name"]: node for node in topology["nodes"]}

        self.assertEqual("Lab3_XSS_CSRF_Complete", topology["project"]["name"])
        self.assertEqual(10, len(nodes))
        self.assertEqual(9, len(topology["links"]))
        self.assertEqual(
            "web-server-lab3-complete",
            topology["templates"][nodes["web-server"]["template"]]["name"],
        )
        self.assertEqual(
            "dns-server-lab3-complete",
            topology["templates"][nodes["dns-server"]["template"]]["name"],
        )

        with (ROOT / "local_templates.json").open("r", encoding="utf-8") as file:
            available = json.load(file)
        resolved = _resolve_templates(topology, available)
        self.assertEqual(
            "d160fead-44f2-4133-abb0-c1d528361232",
            resolved["web_server"]["template_id"],
        )
        self.assertEqual(
            "59993670-3928-41c2-98fa-f0bf4061d7a5",
            resolved["dns_server"]["template_id"],
        )

    def test_lab3_start_uses_requested_templates_and_lab2_complete_baseline(self):
        _, topology = load_topology(LAB3_START_TOPOLOGY_PATH)
        nodes = {node["name"]: node for node in topology["nodes"]}

        self.assertEqual("Lab3_XSS_CSRF_Start", topology["project"]["name"])
        self.assertEqual(10, len(nodes))
        self.assertEqual(9, len(topology["links"]))
        self.assertEqual(
            "web-server-lab3-vulnerable",
            topology["templates"][nodes["web-server"]["template"]]["name"],
        )
        self.assertEqual(
            "dns-server-lab3-complete",
            topology["templates"][nodes["dns-server"]["template"]]["name"],
        )
        self.assertEqual(
            "client-lab1-complete",
            topology["templates"][nodes["client1"]["template"]]["name"],
        )

        with (ROOT / "local_templates.json").open("r", encoding="utf-8") as file:
            available = json.load(file)
        resolved = _resolve_templates(topology, available)
        self.assertEqual(
            "7fb413cc-3e0f-4a1c-8051-507098651341",
            resolved["web_server"]["template_id"],
        )
        self.assertEqual(
            "59993670-3928-41c2-98fa-f0bf4061d7a5",
            resolved["dns_server"]["template_id"],
        )

    def test_lab3_start_restores_dns_paths_and_vulnerable_web_services(self):
        config_dir = LAB3_START_TOPOLOGY_PATH.parent / "configs"
        client1 = (config_dir / "client1.cfg").read_text(encoding="utf-8")
        client2 = (config_dir / "client2.cfg").read_text(encoding="utf-8")
        dns_server = (config_dir / "dns-server.cfg").read_text(encoding="utf-8")
        web_server = (config_dir / "web-server.cfg").read_text(encoding="utf-8")

        self.assertIn("nameserver 127.0.0.1", client1)
        self.assertIn("dnsmasq", client1)
        self.assertIn("nameserver 10.10.20.10", client2)
        self.assertIn("named", dns_server)
        self.assertIn("/opt/exp3/start-exp3.sh", web_server)

    def test_lab2_complete_uses_required_complete_templates(self):
        _, topology = load_topology(LAB2_COMPLETE_TOPOLOGY_PATH)
        nodes = {node["name"]: node for node in topology["nodes"]}

        self.assertEqual("Lab2_HTTPS_Complete", topology["project"]["name"])
        self.assertEqual(10, len(nodes))
        self.assertEqual(9, len(topology["links"]))
        self.assertEqual(
            "web-server-lab2-complete",
            topology["templates"][nodes["web-server"]["template"]]["name"],
        )
        self.assertEqual(
            "dns-server-lab2-complete",
            topology["templates"][nodes["dns-server"]["template"]]["name"],
        )

        with (ROOT / "local_templates.json").open("r", encoding="utf-8") as file:
            available = json.load(file)
        resolved = _resolve_templates(topology, available)
        self.assertEqual(
            "5d045fd1-588d-4609-8be3-df1656f1a62c",
            resolved["web_server"]["template_id"],
        )
        self.assertEqual(
            "b248957c-8ee0-4a1d-bfe6-d7f46c26bcaf",
            resolved["dns_server"]["template_id"],
        )

    def test_lab2_starter_uses_required_templates_and_lab1_baseline(self):
        _, topology = load_topology(LAB2_STARTER_TOPOLOGY_PATH)
        nodes = {node["name"]: node for node in topology["nodes"]}

        self.assertEqual("Lab2_HTTPS_Starter", topology["project"]["name"])
        self.assertEqual(10, len(nodes))
        self.assertEqual(9, len(topology["links"]))
        self.assertEqual(
            "web-server-lab2-no-https",
            topology["templates"][nodes["web-server"]["template"]]["name"],
        )
        self.assertEqual(
            "dns-server-lab2-complete",
            topology["templates"][nodes["dns-server"]["template"]]["name"],
        )
        self.assertEqual(
            "client-lab1-complete",
            topology["templates"][nodes["client1"]["template"]]["name"],
        )

        with (ROOT / "local_templates.json").open("r", encoding="utf-8") as file:
            available = json.load(file)
        resolved = _resolve_templates(topology, available)
        self.assertEqual(
            "6a0da828-1b65-4220-88d8-51b64a7b677f",
            resolved["web_server"]["template_id"],
        )
        self.assertEqual(
            "b248957c-8ee0-4a1d-bfe6-d7f46c26bcaf",
            resolved["dns_server"]["template_id"],
        )

    def test_lab2_starter_preserves_dns_paths(self):
        config_dir = LAB2_STARTER_TOPOLOGY_PATH.parent / "configs"
        client1 = (config_dir / "client1.cfg").read_text(encoding="utf-8")
        client2 = (config_dir / "client2.cfg").read_text(encoding="utf-8")
        dns_server = (config_dir / "dns-server.cfg").read_text(encoding="utf-8")

        self.assertIn("nameserver 127.0.0.1", client1)
        self.assertIn("dnsmasq", client1)
        self.assertIn("nameserver 10.10.20.10", client2)
        self.assertIn("named", dns_server)
        self.assertNotIn("networking-experiments.nju-slab.cn", dns_server)

    def test_lab1_complete_uses_selected_complete_templates(self):
        _, topology = load_topology(LAB1_COMPLETE_TOPOLOGY_PATH)
        nodes = {node["name"]: node for node in topology["nodes"]}

        self.assertEqual("Lab1_Web_DNS_Complete", topology["project"]["name"])
        self.assertEqual(
            "client-lab1-complete",
            topology["templates"][nodes["client1"]["template"]]["name"],
        )
        self.assertEqual(
            "web-server-lab1-complete",
            topology["templates"][nodes["web-server"]["template"]]["name"],
        )
        self.assertEqual(
            "dns-server-lab1-complete",
            topology["templates"][nodes["dns-server"]["template"]]["name"],
        )
        self.assertEqual("client", nodes["administrator"]["template"])
        self.assertEqual("client", nodes["client2"]["template"])

        with (ROOT / "local_templates.json").open("r", encoding="utf-8") as file:
            available = json.load(file)
        resolved = _resolve_templates(topology, available)
        self.assertEqual(
            {
                "client_complete": "4446a559-4668-44ad-be34-4954bb89d04d",
                "web_server": "5f3ecea0-61ba-4b37-a740-b60e2e0603df",
                "dns_server": "705c84f8-b08e-4cf2-b68a-587b3be5eaad",
            },
            {
                alias: resolved[alias]["template_id"]
                for alias in ("client_complete", "web_server", "dns_server")
            },
        )

    def test_lab1_complete_enables_client1_local_dns_cache(self):
        config_dir = LAB1_COMPLETE_TOPOLOGY_PATH.parent / "configs"
        client1 = (config_dir / "client1.cfg").read_text(encoding="utf-8")
        client2 = (config_dir / "client2.cfg").read_text(encoding="utf-8")

        self.assertIn("nameserver 127.0.0.1", client1)
        self.assertIn("dnsmasq", client1)
        self.assertIn("nameserver 10.10.20.10", client2)
        self.assertNotIn("dnsmasq", client2)

    def test_duplicate_link_endpoint_is_rejected(self):
        _, topology = load_topology(LAB1_TOPOLOGY_PATH)
        invalid = copy.deepcopy(topology)
        invalid["links"][1]["endpoints"][0] = copy.deepcopy(
            invalid["links"][0]["endpoints"][0]
        )

        with self.assertRaisesRegex(TopologyError, "端口被重复连接"):
            validate_topology(invalid, LAB1_TOPOLOGY_PATH.parent)

    def test_lab1_topology_is_valid_and_uses_template_names(self):
        _, topology = load_topology(LAB1_TOPOLOGY_PATH)

        self.assertEqual(10, len(topology["nodes"]))
        self.assertEqual(9, len(topology["links"]))
        self.assertTrue(topology["project"]["stop_after_build"])
        self.assertEqual(
            {
                "nat": "NAT",
                "ethernet_switch": "Ethernet switch",
                "core_router": "Cisco IOSv",
                "client": "client-lab1-no-cache",
                "dns_server": "dns-server-lab1-no-recursion",
                "web_server": "web-server-lab1-vulnerable",
            },
            {
                alias: spec["name"]
                for alias, spec in topology["templates"].items()
            },
        )
        self.assertTrue(
            all("template_id" not in spec for spec in topology["templates"].values())
        )
        docker_configs = [
            node["config"]["driver"]
            for node in topology["nodes"]
            if node.get("config") and node["template"] != "core_router"
        ]
        self.assertEqual(["docker_start"] * 5, docker_configs)

    def test_lab1_directory_contains_topology_configs_and_readme(self):
        lab1_dir = LAB1_TOPOLOGY_PATH.parent
        entries = {entry.name for entry in lab1_dir.iterdir()}

        self.assertIn("configs", entries)
        self.assertIn("topology.json", entries)
        self.assertIn("README.md", entries)
        self.assertTrue(
            all(
                name == "configs"
                or name == "README.md"
                or name.endswith(".json")
                for name in entries
            )
        )

    def test_lab1_prescribed_templates_exist_in_local_template_snapshot(self):
        _, topology = load_topology(LAB1_TOPOLOGY_PATH)
        with (ROOT / "local_templates.json").open("r", encoding="utf-8") as file:
            available = json.load(file)

        resolved = _resolve_templates(topology, available)

        self.assertEqual(
            {
                "core_router": "da876787-5b1a-4a8c-b653-8803b4e3ba9c",
                "client": "70d800b2-a225-4626-bc3b-3889e3e89e20",
                "dns_server": "b862d2cc-3f5d-4d13-81db-f91992363d4d",
                "web_server": "a00a124e-8240-47b8-802a-798464dc589d",
            },
            {
                alias: resolved[alias]["template_id"]
                for alias in (
                    "core_router",
                    "client",
                    "dns_server",
                    "web_server",
                )
            },
        )
        self.assertEqual(
            {
                "client": {
                    "adapters": 2,
                    "compute_id": "vm",
                    "image": "ghcr.io/myywee/client:lab1-no-cache",
                    "template_type": "docker",
                },
                "dns_server": {
                    "adapters": 2,
                    "compute_id": "vm",
                    "image": "ghcr.io/myywee/dns-server:lab1-no-recursion",
                    "template_type": "docker",
                },
                "web_server": {
                    "adapters": 2,
                    "compute_id": "vm",
                    "image": "ghcr.io/myywee/web-server:lab1-vulnerable",
                    "template_type": "docker",
                },
                "core_router": {
                    "adapters": 4,
                    "compute_id": "vm",
                    "hda_disk_image": "vios-adventerprisek9-m.spa.159-3.m6.qcow2",
                    "template_type": "qemu",
                },
            },
            {
                alias: {
                    key: resolved[alias][key]
                    for key in expected_keys
                }
                for alias, expected_keys in {
                    "client": ("adapters", "compute_id", "image", "template_type"),
                    "dns_server": (
                        "adapters",
                        "compute_id",
                        "image",
                        "template_type",
                    ),
                    "web_server": (
                        "adapters",
                        "compute_id",
                        "image",
                        "template_type",
                    ),
                    "core_router": (
                        "adapters",
                        "compute_id",
                        "hda_disk_image",
                        "template_type",
                    ),
                }.items()
            },
        )

    def test_build_uses_only_the_declarative_topology(self):
        state_path = ROOT / "tests" / "ignored-state.json"
        with (
            patch("topology_build.GNS3Client", FakeGNS3Client),
            patch("topology_build._write_state") as write_state,
            patch("builtins.print"),
        ):
            state = build_topology(
                LAB1_TOPOLOGY_PATH, state_path=state_path, apply_config=False
            )

        client = FakeGNS3Client.instance
        self.assertEqual(10, len(client.created_nodes))
        self.assertEqual(9, len(client.created_links))
        self.assertEqual(10, len(client.started_nodes))
        self.assertEqual(6, len(client.stopped_nodes))
        self.assertEqual([], client.deleted_projects)
        self.assertEqual("project-id", state["project_id"])
        self.assertFalse(state["configured"])
        self.assertTrue(state["nodes_stopped"])
        self.assertEqual(4, len(state["always_running_nodes"]))
        self.assertEqual(6, len(state["stopped_nodes"]))
        self.assertEqual(2, write_state.call_count)
        write_state.assert_called_with(state_path, state)

    def test_lab1_docker_config_is_written_before_nodes_start(self):
        state_path = ROOT / "tests" / "ignored-lab1-state.json"
        with (
            patch("topology_build.GNS3Client", FakeGNS3Client),
            patch("topology_build._write_state"),
            patch("topology_build.config_router"),
            patch("topology_build.config_raw") as config_raw,
            patch("builtins.print"),
        ):
            state = build_topology(
                LAB1_TOPOLOGY_PATH,
                state_path=state_path,
                apply_config=True,
            )

        client = FakeGNS3Client.instance
        self.assertEqual(5, len(client.updated_nodes))
        first_start = next(
            index for index, event in enumerate(client.events) if event[0] == "start"
        )
        update_indexes = [
            index for index, event in enumerate(client.events) if event[0] == "update"
        ]
        self.assertTrue(all(index < first_start for index in update_indexes))
        self.assertTrue(state["configured"])
        self.assertTrue(state["nodes_stopped"])
        self.assertEqual(6, len(client.stopped_nodes))
        self.assertEqual(
            {"nat", "sw-server", "sw-mgmt", "sw-client"},
            set(state["always_running_nodes"]),
        )
        last_start = max(
            index for index, event in enumerate(client.events) if event[0] == "start"
        )
        stop_indexes = [
            index for index, event in enumerate(client.events) if event[0] == "stop"
        ]
        self.assertTrue(all(index > last_start for index in stop_indexes))
        config_raw.assert_not_called()

        commands_by_node = {
            node_id: shlex.split(properties["start_command"])
            for _, node_id, properties in client.updated_nodes
        }
        self.assertEqual("/bin/bash", commands_by_node["node-client1"][0])
        self.assertEqual("-lc", commands_by_node["node-client1"][1])
        self.assertIn(
            "ip addr add 10.10.30.10/24 dev eth0",
            commands_by_node["node-client1"][2],
        )
        self.assertTrue(commands_by_node["node-client1"][2].endswith("exec /bin/bash"))

    def test_build_stops_nodes_when_device_configuration_fails(self):
        state_path = ROOT / "tests" / "ignored-failed-state.json"
        snapshots = []

        def capture_state(path, state):
            snapshots.append((path, copy.deepcopy(state)))

        with (
            patch("topology_build.GNS3Client", FakeGNS3Client),
            patch("topology_build.configure_docker_start_commands"),
            patch(
                "topology_build.configure_nodes",
                side_effect=RouterConfigError("模拟 IOS 配置失败"),
            ),
            patch("topology_build._write_state", side_effect=capture_state),
            patch("builtins.print"),
            self.assertRaisesRegex(RouterConfigError, "模拟 IOS 配置失败"),
        ):
            build_topology(
                LAB1_TOPOLOGY_PATH,
                state_path=state_path,
                apply_config=True,
            )

        client = FakeGNS3Client.instance
        self.assertEqual(6, len(client.stopped_nodes))
        self.assertEqual([], client.deleted_projects)
        self.assertFalse(snapshots[-1][1]["configured"])
        self.assertTrue(snapshots[-1][1]["nodes_stopped"])
        self.assertEqual(
            "模拟 IOS 配置失败", snapshots[-1][1]["configuration_error"]
        )

    def test_lab1_router_disables_console_logging(self):
        config_path = LAB1_TOPOLOGY_PATH.parent / "configs" / "core-router.cfg"
        commands = [
            line.strip()
            for line in config_path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]

        self.assertIn("no logging console", commands)

    def test_docker_start_command_preserves_shell_quoting(self):
        command = _docker_start_command(
            ["printf 'nameserver 10.10.20.10\\n' > /etc/resolv.conf"]
        )

        self.assertEqual(
            [
                "/bin/bash",
                "-lc",
                "set -e; printf 'nameserver 10.10.20.10\\n' > "
                "/etc/resolv.conf; exec /bin/bash",
            ],
            shlex.split(command),
        )

    def test_reapplying_docker_start_commands_restarts_each_node(self):
        topology_path, topology = load_topology(LAB1_TOPOLOGY_PATH)
        template_ids = {
            "client": "client-lab1-id",
            "dns_server": "dns-lab1-id",
            "web_server": "web-lab1-id",
        }
        client = FakeGNS3Client("http://example.invalid/v2")
        nodes = {}
        for node_spec in topology["nodes"]:
            if node_spec.get("config", {}).get("driver") != "docker_start":
                continue
            runtime = client.create_node_from_template(
                "project-id",
                template_ids[node_spec["template"]],
                node_spec,
                "vm",
            )
            nodes[node_spec["name"]] = runtime
        client.events.clear()

        with patch("builtins.print"):
            configure_docker_start_commands(
                client,
                "project-id",
                topology,
                topology_path.parent,
                nodes,
                restart=True,
            )

        self.assertEqual(5, len(client.stopped_nodes))
        self.assertEqual(5, len(client.updated_nodes))
        self.assertEqual(5, len(client.started_nodes))
        for offset in range(0, len(client.events), 3):
            self.assertEqual(
                ["stop", "update", "start"],
                [event[0] for event in client.events[offset : offset + 3]],
            )

    def test_reconfigure_starts_router_updates_state_and_stops_nodes(self):
        snapshots = []

        def capture_state(path, state):
            snapshots.append((path, copy.deepcopy(state)))

        with (
            patch("topology_build.GNS3Client", FakeGNS3Client),
            patch("topology_build.configure_docker_start_commands"),
            patch("topology_build.configure_nodes"),
            patch("topology_build._write_state", side_effect=capture_state),
            patch("builtins.print"),
        ):
            state = configure_existing(
                LAB1_TOPOLOGY_PATH,
                state_path=LAB1_TOPOLOGY_PATH.parent / "build_state.json",
            )

        client = FakeGNS3Client.instance
        router_id = state["nodes"]["core-router"]["node_id"]
        self.assertIn((state["project_id"], router_id), client.started_nodes)
        self.assertEqual(6, len(client.stopped_nodes))
        self.assertFalse(snapshots[0][1]["configured"])
        self.assertNotIn("configured_at", snapshots[0][1])
        self.assertTrue(snapshots[-1][1]["configured"])
        self.assertTrue(snapshots[-1][1]["nodes_stopped"])

    def test_router_initialization_timeout_is_extended(self):
        self.assertGreaterEqual(ROUTER_INITIALIZATION_TIMEOUT, 600)

    def test_router_config_waits_for_prompts_and_saves(self):
        commands = [
            "hostname Core-Router",
            "interface GigabitEthernet0/0",
            "description SERVER-NETWORK",
            "ip address 10.10.20.1 255.255.255.0",
        ]
        responses = [
            (3, object(), b"Router#"),
            (0, object(), b"terminal length 0\r\nRouter#"),
            (0, object(), b"configure terminal\r\nRouter(config)#"),
            (0, object(), b"hostname Core-Router\r\nCore-Router(config)#"),
            (
                0,
                object(),
                b"interface GigabitEthernet0/0\r\nCore-Router(config-if)#",
            ),
            (
                0,
                object(),
                b"description SERVER-NETWORK\r\nCore-Router(config-if)#",
            ),
            (
                0,
                object(),
                b"ip address 10.10.20.1 255.255.255.0\r\n"
                b"Core-Router(config-if)#",
            ),
            (0, object(), b"end\r\nCore-Router#"),
            (
                0,
                object(),
                b"copy running-config startup-config\r\n"
                b"Destination filename [startup-config]?",
            ),
            (0, object(), b"\r\nBuilding configuration...\r\n[OK]\r\nCore-Router#"),
        ]
        telnet = ScriptedTelnet(responses)

        with (
            patch("utils.telnetlib.Telnet", return_value=telnet) as telnet_class,
            patch("utils.time.sleep"),
            patch("builtins.print"),
        ):
            config_router(5004, commands, host="192.0.2.10")

        telnet_class.assert_called_once_with("192.0.2.10", 5004, timeout=30)
        self.assertEqual(
            [
                b"terminal length 0\r\n",
                b"configure terminal\r\n",
                *(command.encode() + b"\r\n" for command in commands),
                b"end\r\n",
                b"copy running-config startup-config\r\n",
                b"\r\n",
            ],
            telnet.writes,
        )
        self.assertTrue(telnet.closed)

    def test_router_config_stops_when_ios_rejects_a_command(self):
        commands = ["hostname Core-Router", "not-a-real-command"]
        telnet = ScriptedTelnet(
            [
                (3, object(), b"Router#"),
                (0, object(), b"terminal length 0\r\nRouter#"),
                (0, object(), b"configure terminal\r\nRouter(config)#"),
                (0, object(), b"hostname Core-Router\r\nCore-Router(config)#"),
                (
                    0,
                    object(),
                    b"not-a-real-command\r\n% Invalid input detected at '^' marker."
                    b"\r\nCore-Router(config)#",
                ),
            ]
        )

        with (
            patch("utils.telnetlib.Telnet", return_value=telnet),
            patch("utils.time.sleep"),
            patch("builtins.print"),
            self.assertRaisesRegex(RouterConfigError, "IOS 拒绝命令"),
        ):
            config_router(5004, commands)

        self.assertNotIn(b"copy running-config startup-config\r\n", telnet.writes)
        self.assertTrue(telnet.closed)

    def test_router_config_accepts_prompt_only_save_without_readback(self):
        commands = ["hostname Core-Router"]
        telnet = ScriptedTelnet(
            [
                (3, object(), b"Core-Router#"),
                (0, object(), b"terminal length 0\r\nCore-Router#"),
                (0, object(), b"configure terminal\r\nCore-Router(config)#"),
                (0, object(), b"hostname Core-Router\r\nCore-Router(config)#"),
                (0, object(), b"end\r\nCore-Router#"),
                (1, object(), b"Core-Router#"),
            ]
        )

        with (
            patch("utils.telnetlib.Telnet", return_value=telnet),
            patch("utils.time.sleep"),
            patch("builtins.print"),
        ):
            config_router(5004, commands)

        self.assertNotIn(b"show startup-config\r\n", telnet.writes)
        self.assertTrue(telnet.closed)


if __name__ == "__main__":
    unittest.main()
