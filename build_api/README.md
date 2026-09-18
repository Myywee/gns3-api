# 声明式拓扑构建

每个实验目录只保存拓扑数据和设备配置，不再维护一套专用的构建、配置逻辑。

## 使用方式

```powershell
python build_api/topology_build.py validate build_api/lab1-start/topology.json
python build_api/topology_build.py build build_api/lab1-start/topology.json
```

`build` 会依次创建项目、从模板创建节点、连接端口、临时启动节点并应用配置，然后在成功时关闭 Docker、QEMU、VPCS 等可关机节点。运行产生的项目 ID、节点 ID、console 信息和关闭结果保存在实验目录的 `build_state.json`，不会写回 `topology.json`。NAT 和内置 Ethernet switch 是 GNS3 常驻节点类型，没有独立关机状态。

如果构建时使用了 `--no-config`，或需要重新应用配置：

```powershell
python build_api/topology_build.py configure build_api/lab1-start/topology.json
```

IOS 配置会逐条等待设备提示符并检查错误，随后使用
`copy running-config startup-config` 保存。
重新配置时会自动启动待配置的路由器，并按拓扑中的
`stop_after_build` 设置在完成后关闭可关机节点；失败状态也会写入
`build_state.json`，不会继续保留过期的 `configured: true`。

## topology.json 结构

- `project`：项目名、构建期间是否自动启动节点，以及构建成功后是否关闭节点。`stop_after_build` 默认为 `true`。
- `templates`：实验内部使用的模板别名。通过 GNS3 模板 `name` 解析；同名模板不唯一时使用 `template_id`。
- `nodes`：节点名称、模板别名、坐标和配置声明。
- `links`：两个端点的节点名、adapter 和 port。
- `config.driver`：`ios`、`vpcs`、通用的 `raw` Telnet 命令驱动，或把命令写入 Docker 节点 Start command 的 `docker_start`。
- `config.file`：相对于 `topology.json` 的配置文件；也可以改用内联的 `config.commands` 数组。

新增实验时复制目录结构并修改 JSON/配置文件即可，通用构建器本身无需修改。

实验一的初始态和完成态分别见 `lab1-start/README.md` 与 `lab1-complete/README.md`；实验二初始态和完成态分别见 `lab2-start/README.md` 与 `lab2-complete/README.md`；实验三初始态和完成态分别见 `lab3-start/README.md` 与 `lab3-complete/README.md`。实验目录不包含实验专用 Python 入口，统一通过外层 `topology_build.py` 操作。
