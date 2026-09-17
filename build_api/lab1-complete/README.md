# 实验一完成态拓扑

本目录是 `lab1-start` 的完成态版本，网络地址、链路和路由器配置保持一致，使用独立的 GNS3 项目名 `Lab1_Web_DNS_Complete`。

## 完成态节点

| 节点 | 模板 name | 状态 |
|---|---|---|
| `client1` | `client-lab1-complete` | 启动本地 dnsmasq 缓存，DNS 指向 `127.0.0.1` |
| `web-server` | `web-server-lab1-complete` | 使用修复后的 nginx 完成态配置 |
| `dns-server` | `dns-server-lab1-complete` | 使用允许实验所需递归解析的 BIND 完成态配置 |

`administrator` 与 `client2` 仍使用 `client-lab1-no-cache`，作为直接查询 DNS 服务器的对照节点。所有 Docker 配置通过节点实例的 Start command 应用，不修改全局模板。

## 校验、构建与重新配置

```powershell
python build_api/topology_build.py validate build_api/lab1-complete/topology.json
python build_api/topology_build.py build build_api/lab1-complete/topology.json
python build_api/topology_build.py configure build_api/lab1-complete/topology.json
```

构建成功后，Router 和全部 Docker 节点会按照 `stop_after_build` 设置关闭；NAT 和内置交换机保持为 GNS3 常驻节点。
