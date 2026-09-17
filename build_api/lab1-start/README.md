# 实验一拓扑：Web 与 DNS 基础

本目录保存实验一的拓扑定义、运行状态、设备配置和使用说明。模板仅通过 `local_templates.json` 中的 `name` 解析，未把模板 UUID 写入 `topology.json`。所有节点（包括 NAT 与三个内置交换机）都指定在 `vm` compute 上运行，以保持实验链路位于 GNS3 VM。

## 节点与模板

| 节点 | 模板 name | 初始地址 |
|---|---|---|
| `core-router` | `Cisco IOSv` | Gi0/0 `10.10.20.1/24`；Gi0/1 `10.10.10.1/24`；Gi0/2 `10.10.30.1/24`；Gi0/3 DHCP |
| `administrator` | `client-lab1-no-cache` | `10.10.10.10/24` |
| `client1` | `client-lab1-no-cache` | `10.10.30.10/24` |
| `client2` | `client-lab1-no-cache` | `10.10.30.20/24` |
| `dns-server` | `dns-server-lab1-no-recursion` | `10.10.20.10/24` |
| `web-server` | `web-server-lab1-vulnerable` | `10.10.20.20/24` |
| `nat` | `NAT` | GNS3 NAT/DHCP |
| `sw-server`、`sw-mgmt`、`sw-client` | `Ethernet switch` | 无需配置 |

## 连线

| 端点 A | 端点 B | 用途 |
|---|---|---|
| `nat` 0/0 | `core-router` 3/0（Gi0/3） | WAN / DHCP / NAT outside |
| `core-router` 0/0（Gi0/0） | `sw-server` 0/0 | 服务器网段 |
| `core-router` 1/0（Gi0/1） | `sw-mgmt` 0/0 | 管理网段 |
| `core-router` 2/0（Gi0/2） | `sw-client` 0/0 | 客户端网段 |
| `dns-server` 0/0 | `sw-server` 0/1 | DNS 服务器 |
| `web-server` 0/0 | `sw-server` 0/2 | Web 服务器 |
| `administrator` 0/0 | `sw-mgmt` 0/1 | 管理终端 |
| `client1` 0/0 | `sw-client` 0/1 | 客户端 1 |
| `client2` 0/0 | `sw-client` 0/2 | 客户端 2 |

## 初始实验状态

- 路由器配置三个内网网关、DHCP WAN、PAT 和默认路由。
- Linux 节点的 `configs/*.cfg` 会被合并为 `/bin/bash -lc ...`，在节点启动前写入各自的 Docker Start command，用于配置 `eth0`、默认路由和 DNS。
- `dns-server` 启动 BIND，但保持镜像的“禁止公网递归”状态。
- `web-server` 启动 nginx，但保持镜像的易受攻击配置。
- `client1` 初始直连 `10.10.20.10`，不预先启用 dnsmasq；本地缓存仍由学生在实验过程中完成。
- 构建器会临时启动节点以应用 IOS 配置；构建成功后关闭 Router 和全部 Docker 节点。NAT 与内置交换机属于 GNS3 常驻节点，没有独立关机状态。

## 校验、构建与重新配置

在仓库根目录统一通过外部入口执行：

```powershell
python build_api/topology_build.py validate build_api/lab1-start/topology.json
python build_api/topology_build.py build build_api/lab1-start/topology.json
python build_api/topology_build.py configure build_api/lab1-start/topology.json
```

构建器会把运行时项目 ID、节点 ID、console 信息和关闭结果写入 `lab1-start/build_state.json`。该文件由实际构建产生，不属于静态拓扑定义。

构建时不会修改全局 Docker 模板，只更新本项目节点实例的 Start command。Docker 节点以后每次启动都会自动恢复地址、路由、DNS 和对应服务。`configure` 会停止相关 Docker 节点、更新 Start command 并重新启动，使配置文件变更立即生效。

路由器配置由构建器逐条确认 IOS 提示符和错误信息，使用
`copy running-config startup-config` 持久化。
配置中包含 `no logging console`，用于避免 Console 输出无关的系统日志。`configure` 可用于重试：
它会自动启动路由器，成功或失败后均按照 `stop_after_build` 关闭可关机节点。
