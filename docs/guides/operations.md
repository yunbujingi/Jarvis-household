# 备份、恢复与故障处理

## 一致性备份

内置备份使用SQLite备份API，可在服务运行时读取一致性快照，并保存同一密钥。目标目录必须不存在，其父目录必须存在。

```sh
# 使用全新名字；不要覆盖旧备份。
docker compose -f deploy/community/compose.yaml exec household \
  python -m jarvis_home.backup /data/backup-before-upgrade
```

成功输出`backup_verified`，校验包含SQLite integrity_check、全部记录/审计解密和SHA-256清单。该备份仍在同一NAS数据卷；不是离机灾备，也没有自动轮换和保留策略。

本机同样适用：

```sh
JWS_DATA_DIR=.runtime .venv/bin/python -m jarvis_home.backup .runtime-backup-example
```

备份内含`home.sqlite3`、`key`和记录SHA-256/格式版本的`backup.json`，均为0600，目录0700。不要只拷数据库；密钥丢失后不能恢复已有密文，也不能生成新密钥继续读取。

## 恢复演练

在新私有目录或独立数据卷恢复，不覆盖正式库：

```sh
# SOURCE为备份目录，TARGET必须不存在；不会覆盖运行库。
.venv/bin/jarvis-home-restore SOURCE TARGET
JWS_DATA_DIR=TARGET .venv/bin/jarvis-home-mcp
```

恢复先校验清单及密钥，再生成新目录。使用同一request_id和参数核对已完成操作应返回replayed；查询记录与审计一致后，只在恢复测试副本执行撤销，确认原库不变。`jarvis-home-check`自动完成这套隔离演练。清单校验只能检测损坏，不是防攻击者篡改的签名。

旧版无backup.json的备份：先保留原件，将完整数据库+密钥复制到独立0700目录，用新版本backup命令生成带清单的备份，再演练恢复。不要直接在唯一备份上写入。官方接入点不包含在账本备份中，可在官方控制台重新取得；数据密钥丢失无法这样重建。

未完成备份可能留下目标目录；保留失败现场检查，不复用或覆盖该目录。不要使用普通临时文件清理策略处理正式数据库、密钥或备份。

## 常见问题

| 现象 | 检查与处理 |
| --- | --- |
| 容器运行但无工具 | 查看阶段日志、接入点权限、官方控制台刷新；不要仅凭运行状态认定接通 |
| 一直awaiting_configuration | 确认configure与bridge使用相同数据卷和JWS_ENDPOINT_FILE |
| configuration_error | 检查目标域名、文件所有者0600、非符号链接；不输出token |
| authentication_rejected | 在官方控制台核对凭据，使用私密流程替换；不要重置其他桥正在使用的全局接入配置 |
| 超时后不确定是否记账 | 保留request_id重试或查询，不生成新ID重复写入 |
| 多批同名物品 | 查询后按record_id和expected_version操作，不猜批次 |
| 查询不到到期日 | 区分无记录与due=null；不自动估算食品安全期限 |
| 网页与语音数据不同 | 比对数据目录：本机与NAS默认独立，尚无同步功能 |
| 数据目录权限错误 | 0700目录、0600密钥、正确运行UID；不要chmod 777 |

## 观测与延迟

桥接stdout输出JSON：`household_bridge.phase`、`tool_call`（本地随机call_id、白名单tool、elapsed_ms、outcome）、`transport_failure.category`和`retry`（次数、等待秒数）。不记录正文、JSON-RPC id、业务request_id、异常文本或凭据。outcome为success/error/timeout_unknown/interrupted_unknown/cancelled_unknown；unknown表示结果不确定，不表示回滚。

`/tmp/jws-status.json`保存最新阶段和时间，不能单凭旧ready认定进程仍存活。启动、连接、就绪、重连、配置错误分别可见。调用期限20秒、单次I/O5秒、子进程退出宽限3秒；取消会清理本轮协程和子进程。SQLite锁等待5秒。无法通过取消承诺撤销已提交事务。

重连退避2、4、8…最多60秒加0–1秒抖动；稳定运行60秒后重置。配置/认证/协议错误停止连接并保留状态，修正后手动重启。缺配置每10秒检查一次。没有自动重放写入。

Compose日志轮转上限2×2MB；这是大小上限，不是30天保证。非Docker部署应交给有日志轮转的进程管理器，或使用logrotate（2MB、保留2份、copytruncate、0600）；不要无限追加文件。普通日志30天复核，失败证据问题关闭后复核，不附真实正文。

本机文字命令返回elapsed_ms、route和model_calls，不能用作官方语音总耗时。官方链路尚无完整ASR/模型/工具/TTS分段追踪；真人验收记录从说完到开始回复的感知延迟。

明确问题尽量使用一次工具筛选、简短结果。大量库存仍需解密扫描当前records，当前不是面向海量数据库的搜索索引服务。
