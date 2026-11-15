# 开源预览版交付与维护

0.3.0 起采用 MIT；没有公共PyPI包、公共镜像或自动Release。本仓库定位为面向小智的家庭共享账本、物品管理和MCP工具桥。维护范围是当前预览版的缺陷与安全修复，不承诺长期支持周期或服务可用率。

## 交付步骤

1. 在codex/或其他功能分支修改，PR面向main；核对兼容与变更日志。
2. 更新pyproject.toml、Compose镜像标签和CHANGELOG.md为同一版本。依赖变更同时更新requirements.lock及许可清单。
3. 运行测试、ruff、pip check、依赖闭包检查、pip-audit和仓库检查。
4. 构建到该版本专属目录，运行verify_dist.py验证实际wheel和sdist；脚本安装到新的venv，不从原源码目录导入。
5. 运行release_manifest.py，生成build.json（提交、版本、平台、构建输入变更标志）与SHA256SUMS。源码有未提交变更时不能把产物标作干净提交构建。
6. 推送PR，核对最终head对应的CI（checkout明确检出PR head，build.json不使用合并测试临时提交）；检查两个Python环境、安装包、审计及x86_64容器均通过。
7. 正式包沿用dist/下版本专属目录；CI产物默认保留14天，维护者应将需要长期保存的正式包与校验清单另行保管，CI到期不意味着正式交付可删除。
8. 仓库按维护者决定公开；公共 Release、包和镜像仍需单独决定，本工作流不发布这些产物。

```sh
.venv/bin/python -m build --outdir dist/0.4.0a1-preview
.venv/bin/python scripts/verify_dist.py dist/0.4.0a1-preview
.venv/bin/python scripts/release_manifest.py dist/0.4.0a1-preview
```

检查SHA256SUMS：Linux使用`sha256sum -c SHA256SUMS`，macOS使用`shasum -a 256 -c SHA256SUMS`，从产物目录运行。

## 环境与限制

自动测试矩阵为Ubuntu24.04 x86_64、Python3.12/3.13；容器仅验证Python3.12 Linux x86_64。本地另验证macOS arm64/Python3.12。0.3.0已完成一次x86_64 NAS真人验收；ARM64容器与其他目标NAS仍需单独验收；Windows的信号处理与权限语义未经适配。

升级前必须保留旧镜像/配置和数据库+密钥备份。0.3.0沿用数据库版本1；已用新纠错参数写入后，旧程序不保证重放新请求。回滚以升级前完整备份为边界，详见[数据模型](data-model.md)和[部署指南](deployment.md)。

## CI信任边界

CI只有contents:read，不使用生产凭据、不配置部署环境、不启用pull_request_target、不推送镜像。Actions使用经GitHub官方仓库tag API核实的完整提交固定。PR不可信代码只访问临时测试数据；不得为排查失败向其添加正式密钥。

ruff仅启用F/E9正确性检查，避免为格式重写代码。漏洞扫描覆盖锁定的直接、间接和开发依赖；依赖闭包检查先确认未漏包。服务不可达/扫描工具故障会令任务失败，不能写成“无漏洞”；不会全局忽略告警。扫描是已知漏洞查询，不能证明没有未知风险。
