# 备份、恢复与故障处理

## 一致性备份

内置备份使用SQLite备份API，可在服务运行时读取一致性快照，并保存同一密钥。目标目录必须不存在，其父目录必须存在。

```sh
# 使用全新名字；不要覆盖旧备份。
docker compose -f deploy/community/compose.yaml exec household \
  python -m jarvis_home.backup /data/backup-before-upgrade
```

成功输出`backup_verified`，校验包含SQLite integrity_check。该备份仍在同一NAS数据卷；不是离机灾备，也没有自动轮换和保留策略。

本机同样适用：

```sh
JWS_DATA_DIR=.runtime .venv/bin/python -m jarvis_home.backup .runtime-backup-example
```

备份内含`home.sqlite3`和`key`，均为0600，目录0700。不要只拷数据库；密钥丢失后不能恢复已有密文，也不能生成新密钥继续读取。

## 恢复演练

在新私有目录或独立数据卷恢复，不覆盖正式库：

1. 复制数据库与密钥，核对目录/文件权限和运行UID。
2. 用Store打开，检查密钥校验、数据库版本及完整性。
3. 核对预期物品/账目/审计，再在隔离库中验证撤销。
4. 确认恢复数据无误后才计划正式切换，切换前另保留当前库。

本仓库`tests/test_backup.py`覆盖内容一致、恢复后撤销和原库不变；它不替代每台NAS的灾备演练。

## 常见问题

| 现象 | 检查与处理 |
| --- | --- |
| 容器运行但无工具 | 查看阶段日志、接入点权限、官方控制台刷新；不要仅凭运行状态认定接通 |
| 一直awaiting_configuration | 确认configure与bridge使用相同数据卷和JWS_ENDPOINT_FILE |
| configuration_rejected | 检查目标域名、文件所有者0600、非符号链接；不输出token |
| authentication_rejected | 在官方控制台核对凭据，使用私密流程替换；不要重置其他桥正在使用的全局接入配置 |
| 超时后不确定是否记账 | 保留request_id重试或查询，不生成新ID重复写入 |
| 多批同名物品 | 查询后按record_id和expected_version操作，不猜批次 |
| 查询不到到期日 | 区分无记录与due=null；不自动估算食品安全期限 |
| 网页与语音数据不同 | 比对数据目录：本机与NAS默认独立，尚无同步功能 |
| 数据目录权限错误 | 0700目录、0600密钥、正确运行UID；不要chmod 777 |

## 观测与延迟

桥接记录固定阶段，不记录正文或凭据。本机文字命令返回elapsed_ms、route和model_calls，不能用作官方语音总耗时。官方链路尚无完整ASR/模型/工具/TTS分段追踪；真人验收记录从说完到开始回复的感知延迟。

明确问题尽量使用一次工具筛选、简短结果。大量库存仍需解密扫描当前records，当前不是面向海量数据库的搜索索引服务。
