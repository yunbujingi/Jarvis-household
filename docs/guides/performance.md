# 性能与故障基准

从开发环境运行：

```sh
.venv/bin/python scripts/benchmark.py --samples 100
```

脚本创建独占测试目录、真实stdio子进程和仅监听127.0.0.1的临时WebSocket服务；退出时关闭服务、回收进程并清理自己创建的夹具。无凭据、无外网连接、无设备动作。

分别测量：

- local_tool：同进程FastMCP调用+验证+SQLite查询。
- loopback_bridge：本地WebSocket往返+真实bridge.relay+stdio MCP+SQLite查询。

每组预热1次、串行100次，空测试库存、scope=items、limit=3；P50/P95使用nearest-rank。进程启动和初始化不计入样本。此基准用于发现工具层回归，不是高库存吞吐、WAN延迟、NAS性能或完整语音延迟。官方ASR、LLM与TTS不在测量范围。

2026-11-15本地macOS arm64/Python3.12基准见[验收说明](verification.md)；每次CI分别保存Linux矩阵的benchmark.json，不设置跨平台硬性毫秒门槛。

故障测试使用同一套回环桥和真实SQLite：响应丢失、已提交后超时、协议取消、子进程退出、断线及下一次连接恢复。测试确认unknown结果不等于回滚，同一业务request_id重试只返回原结果。指数退避分类另用可控时钟验证，防止测试等待真实分钟级退避。
