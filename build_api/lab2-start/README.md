# 实验二初始拓扑：HTTPS

本目录以实验一完成态为基础，作为实验二的初始环境。拓扑继续使用三个隔离网段、Cisco IOSv 路由器、NAT 和三个内置交换机。

按照实验说明，初始状态必须满足：

- `networking-experiments.nju-slab.cn` 尚未配置为本地区域，应由 BIND 递归查询公网 DNS，结果不得为 `10.10.20.20`。
- Web 节点尚未启用 HTTPS，实验过程中再部署 `/var/www/portal`、缓存/CORS、证书和 301 跳转。
- 保留实验一的 Router PAT、BIND 递归解析、`experiment.test` 区域以及 Client1 本地 dnsmasq 配置。

关键模板：

- `web-server`：`web-server-lab2-no-https`，初始仅提供 HTTP，供实验中配置 HTTPS。
- `dns-server`：`dns-server-lab2-complete`，提供实验二所需的完整 DNS 状态。
- `client1`：`client-lab1-complete`，保留实验一完成后的本地 DNS 缓存能力。
- `administrator`、`client2`：`client-lab1-no-cache`。

地址和链路与实验一保持一致：DNS 为 `10.10.20.10/24`，Web 为 `10.10.20.20/24`，管理员为 `10.10.10.10/24`，两个客户端分别为 `10.10.30.10/24` 和 `10.10.30.20/24`。

构建完成并启动节点后，应先确认 `dig @127.0.0.1 networking-experiments.nju-slab.cn A +noall +answer` 返回公网地址。如果镜像可写层中残留实验二区域配置，需要先清理残留状态，再开始实验。

在仓库根目录执行：

```powershell
python build_api/topology_build.py validate build_api/lab2-start/topology.json
python build_api/topology_build.py build build_api/lab2-start/topology.json
python build_api/topology_build.py configure build_api/lab2-start/topology.json
```

Docker 配置通过节点实例的 Start command 应用；构建器临时启动设备完成配置后，按照 `stop_after_build` 关闭 Router 和全部 Docker 节点。
