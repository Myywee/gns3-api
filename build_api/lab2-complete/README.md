# 实验二完成态拓扑：HTTPS

本目录保存实验二完成态。网络结构、地址、Router PAT、实验一 DNS 基线和 Client1 本地 dnsmasq 与实验二初始态一致。

关键模板：

- `web-server`：`web-server-lab2-complete`
- `dns-server`：`dns-server-lab2-complete`
- `client1`：`client-lab1-complete`
- `administrator`、`client2`：`client-lab1-no-cache`

完成态预期包含 `networking-experiments.nju-slab.cn` 的本地 DNS 记录、Web 主页、缓存与 CORS 策略、HTTPS 配置以及 HTTP 到 HTTPS 的 301 跳转。这些应用内容由所选 complete 镜像提供；本目录配置负责恢复节点地址、路由、DNS，并启动 BIND、nginx 和 dnsmasq。

在仓库根目录执行：

```powershell
python build_api/topology_build.py validate build_api/lab2-complete/topology.json
python build_api/topology_build.py build build_api/lab2-complete/topology.json
python build_api/topology_build.py configure build_api/lab2-complete/topology.json
```

构建器临时启动设备完成配置后，按照 `stop_after_build` 关闭 Router 和全部 Docker 节点。
