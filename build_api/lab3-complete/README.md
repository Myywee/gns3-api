# 实验三完成态拓扑：XSS 与 CSRF

本目录从实验二完成态继续，保留相同的网络、地址、Router PAT、Client1 本地 DNS 缓存和 HTTPS 实验基础。

关键模板：

- `web-server`：`web-server-lab3-complete`
- `dns-server`：`dns-server-lab3-complete`
- `client1`：`client-lab1-complete`
- `administrator`、`client2`：`client-lab1-no-cache`

Web 镜像提供实验三完成态应用，包括 XSS 输出转义、HttpOnly Cookie、CSRF Token 校验、Token 轮换和 SameSite 防御，并保留攻击者静态站点、nginx 双虚拟主机和启动脚本；DNS 镜像提供两个实验域名的完整区域。拓扑配置负责恢复地址、路由与 DNS，并启动对应服务。

在仓库根目录执行：

```powershell
python build_api/topology_build.py validate build_api/lab3-complete/topology.json
python build_api/topology_build.py build build_api/lab3-complete/topology.json
python build_api/topology_build.py configure build_api/lab3-complete/topology.json
```

构建成功后，Router 和全部 Docker 节点会按照 `stop_after_build` 自动关闭。开始实验时在 GNS3 中启动节点即可；Docker Start command 会恢复各节点网络配置并启动 BIND、nginx、Flask 和 dnsmasq。
