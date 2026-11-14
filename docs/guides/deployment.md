# 从源码部署

## 适用范围

`deploy/community/`用于新安装，Python3.12基础镜像，依赖从包源安装。它与已验收NAS上使用的离线增量包不同；不要将新模板直接覆盖已有生产项目。历史离线包和真实部署截图不进入仓库。

镜像不包含账本或接入点；`.dockerignore`只允许打包源码、项目元数据和README。Dockerfile的构建上下文是仓库根目录，路径遵循[Compose构建规范](https://docs.docker.com/reference/compose-file/build/)。

```sh
docker compose -f deploy/community/compose.yaml config
docker compose -f deploy/community/compose.yaml build
docker compose -f deploy/community/compose.yaml run --rm household jarvis-home-configure
docker compose -f deploy/community/compose.yaml up -d
```

在官方小智的目标智能体中取得MCP接入点，交互配置时粘贴到隐藏输入。不要上传此地址，也不要把它写进shell命令。`configure`拒绝覆盖已有凭据；首次配置失败时检查权限与输入，不要删除账本密钥。

## 容器与数据

| 配置 | 默认 |
| --- | --- |
| 项目名 | jws-household-example |
| 服务 | household |
| 用户 | 10001:10001 |
| 数据卷 | 项目前缀 + household_data，挂载/data |
| 账本 | /data/ledger |
| 接入点 | /data/endpoint，0600且属于运行用户 |
| 内存 / CPU / 进程数 | 256MB / 0.5 / 64 |
| 根文件系统 | 只读；/tmp为16MB临时文件系统 |
| 特权 | 无capability，no-new-privileges，不挂Docker socket |
| 公网端口 | 无 |
| 重启策略 | unless-stopped |

首次由镜像初始化的数据卷目录属于UID10001。若自行改用主机绑定目录，必须提前按相同用户/权限准备，不能通过给所有人写权限解决问题。

## 连接验收

```sh
docker compose -f deploy/community/compose.yaml logs --tail 30 household
docker compose -f deploy/community/compose.yaml exec household python -c 'import json; print(json.load(open("/tmp/jws-status.json")))'
```

- awaiting_configuration：尚未配置接入点。
- connected：WSS已建立。
- ready：MCP初始化响应已成功发出。
- reconnecting：暂时断线，正在退避重试。
- configuration_rejected / authentication_rejected / protocol_or_tls_error：停止连接，需处理。

随后在官方控制台核对三个账本工具与原工具共存。保留原模型与音色，不因增加账本而重置全局接入点。最后按[验收说明](verification.md)完成真实语音测试。

## 升级与回滚

1. 保存当前Compose、镜像标签/镜像导出、数据库与密钥一致性备份。
2. 确认新版本工具参数与数据库版本兼容；先在隔离数据卷测试。
3. 只更新本项目镜像，沿用原项目名、服务名及原数据卷。切换期间账本工具会短暂断线。
4. 核对镜像版本、日志、官方工具列表及原数据；不要只看“运行中”。
5. 出现不兼容时停止新容器、恢复旧配置/镜像，保留数据卷。数据库迁移不可逆时必须用匹配版本备份恢复，不能盲目降级。

不要执行`down -v`清理正式部署；这会删除卷。只停用服务可用`docker compose ... stop`。不需要对官网、Nginx、DNS、HA或宠物服务做修改。

## 本机替代方式

不使用Docker时，安装项目后设置JWS_DATA_DIR与JWS_ENDPOINT_FILE到私有目录，运行jarvis-home-configure，再运行jarvis-home-bridge。只有官方桥需要网络；本机网页jarvis-home与stdio工具jarvis-home-mcp可以独立运行。配置长期进程管理与重启前，应先验证权限和数据目录。
