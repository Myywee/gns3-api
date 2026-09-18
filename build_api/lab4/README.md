# 实验四：CUBIC 与 BBR 拥塞控制对比

依据《实验四_CUBIC与BBR拥塞控制对比_GNS3设计方案》生成。
本目录通过外层 `topology_build.py` 构建，不需要实验专用 Python 文件。

## 模板、地址与连线

| 节点 | GNS3 模板 name | 镜像 / 地址 |
|---|---|---|
| client | client-lab4-complete | `ghcr.io/myywee/client:lab4-complete`；eth0 `10.10.10.10/24`，网关 `10.10.10.1` |
| Router | Cisco IOSv | 不下发设备配置，保留模板默认状态 |
| server | server-lab4-complete | `ghcr.io/myywee/server:lab4-complete`；eth0 `10.20.20.20/24`，网关 `10.20.20.1` |

镜像名取自项目现有 `local_templates.json`；构建时按 name 查找 GNS3 服务端已注册模板，所有节点使用 `vm` compute。

| 连线 | GNS3 adapter/port |
|---|---|
| client eth0 — Router Gi0/0 | client 0/0 — Router 0/0 |
| Router Gi0/1 — server eth0 | Router 1/0 — server 0/0 |

Client 和 Server 位于不同网段。本目录不配置 Router，因此构建完成本身不保证两个网段互通；连通性取决于 Router 已有的接口和路由配置。

## 构建

在项目根目录执行：

```powershell
python build_api/topology_build.py validate build_api/lab4/topology.json
python build_api/topology_build.py build build_api/lab4/topology.json
```

Docker 地址命令写入节点的 Start command，每次启动生效。配置优先使用镜像中的 `ip`，否则使用 `/gns3/bin/busybox ip`。构建器自动添加交互 Bash 入口。
构建成功后关闭全部三个节点，项目状态记录于生成的 `build_state.json`。

Router 的 GNS3 节点名称为 `Router`，没有 `config` 声明或配套配置文件。构建器不会向 Router 下发 IP、hostname、接口启用或保存配置命令；IOS 内部主机名由模板或已有配置决定。修改本地文件不会重命名已有 GNS3 节点，也不会清除设备上的已有配置。

需要重新应用 Client、Server 配置时（Router 不下发配置）：

```powershell
python build_api/topology_build.py configure build_api/lab4/topology.json
```

## 构建后设置实验条件

当前通用构建器只创建链路，不设置 Packet filters。开始测量前，在 GNS3 中对 **Router—server** 链路设置：

- Delay Latency：25 ms。
- Jitter：2 ms。
- Packet loss：初始 0%；每轮 30 秒时设为 2%，50 秒时恢复 0%。

恢复丢包率时保留 Delay/Jitter，不使用 Suspend 或清空全部过滤器。
本拓扑未自动配置 20 Mbit/s 限速。按设计方案第 3.4 节，若工程已有 20 Mbit/s 瓶颈则保持，否则测量并记录实际可用带宽，保证各轮和实验五链路条件一致。

## 启动与检查

在 GNS3 启动全部节点，Router 已具备跨网段转发条件时，在 client 执行：

```bash
ping -c 3 10.10.10.1
ping -c 3 10.20.20.20
cat /proc/sys/net/ipv4/tcp_available_congestion_control
command -v iperf3 ss tc tcpdump
```

拥塞控制列表必须同时包含 `cubic` 和 `bbr`。BBR 依赖 GNS3 VM 宿主内核，镜像标签不能保证内核支持；缺少时由环境维护者在宿主侧启用。节点启动配置不会加载内核模块或修改宿主参数。
宿主支持且容器权限允许时，可按设计方案在 client 执行 `tc qdisc replace dev eth0 root fq`，并用 `tc qdisc show dev eth0` 检查。

在 server 终端启动接收端：

```bash
iperf3 -s -p 5201
```

接收端未写入 Start command，便于按照方案在终端观察和停止。实验脚本、抓包、90 秒测试和证据采集按原设计方案第 5 节执行；本目录不自动运行测试，也不假定 complete 镜像中已存在观测脚本。导出实验结果后再删除或重建节点。
