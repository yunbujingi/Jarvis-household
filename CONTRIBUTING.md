# 参与开发

当前仓库处于私人整理阶段。请先在 Issue 中说明用户场景、预期行为和现有缺口；不要上传家庭数据或控制台接入点。

## 环境与工作流

使用 Python 3.12，在仓库根目录创建 `.venv`，安装 `pip install -e '.[dev]'`。从 `main` 创建功能分支，保持一次改动解决一个问题。

1. 阅读 README、架构与相关模块，检查 Git 状态。
2. 采用最小修改，保持现有字段与工具调用兼容。
3. 涉及数据写入时覆盖幂等、事务失败、撤销和版本冲突；涉及日期时覆盖北京时间的边界。
4. 运行 `pytest -q`、`python -m compileall -q src`、`pip check`、`python -m build`。
5. 暂存文件后运行 `python scripts/check_repository.py`，审查 `git diff --cached`。
6. PR 说明问题、行为变化、验证证据、数据兼容与未完成项。

不要通过删除功能或返回伪造设备结果让测试通过。测试只用临时目录和明确测试值，不读取 `.runtime`。自动化测试不向真实家庭设备发指令。

## UI 与图片

本机网页如有变更，检查桌面/窄屏、长文本、空状态、错误及加载状态。公开截图只能来自隔离演示数据，必须标注为演示，不能上传真实账本页面。

`docs/images/` 中的拓扑图由 `scripts/render_diagrams.py` 生成，编辑脚本后同时更新 SVG 与 PNG。绘图需要 Pillow；字体使用本机 PingFang 或 Noto CJK，脚本支持 `JWS_DIAGRAM_FONT` 指定字体路径。

## 依赖与许可证

运行依赖由 `pyproject.toml` 定义；`requirements.lock` 是已验证环境快照，包含开发依赖，不是带哈希的跨平台锁文件。更新依赖需说明原因并重新执行测试、构建和部署验证。公开发布前确认项目许可证与第三方许可兼容，不将外部项目代码或图片无来源复制进来。
