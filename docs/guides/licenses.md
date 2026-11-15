# 来源与许可复核清单

本表由锁定环境的包元数据生成，详细版本、上游链接与安装包内许可证文件SHA-256见[dependencies.json](dependencies.json)。运行 `python scripts/dependencies.py --output docs/guides/dependencies.json` 可复核；平台相关包的文件清单可能不同。元数据声明不等于人工或法律合规认证。

## 第一方与图示

| 范围 | 来源与处理 |
| --- | --- |
| src、tests、scripts、部署模板、文档 | 本仓库第一方实现与维护历史；未复制外部家居/小佩项目源码。项目许可证待维护者决定 |
| topology / request-flow SVG、PNG | scripts/render_diagrams.py生成的原创技术图；不含真实家庭数据或截图 |
| 图中文字 | 系统字体绘制；未分发字体二进制。SVG仅引用字体名称，PNG仅含栅格结果；再分发前维护者须复核所用字体条款 |
| 绘图工具Pillow | 仅制作图片使用，不是运行依赖；使用者需遵守其HPND许可，重绘可使用自行合法取得的Noto CJK字体 |
| 小智 / Home Assistant / 猫咪服务 | 外部协议/服务边界；没有把这些项目的许可当作本项目授权 |
| Python / Debian基础镜像 | 由官方镜像提供，镜像内各包有独立许可；本轮不发布镜像，后续分发需保留镜像许可证与源代码义务材料 |

## 直接与间接依赖

已人工核对五个直接依赖所带LICENSE文件：cryptography为Apache-2.0或BSD-3-Clause双许可；FastAPI和MCP为MIT；Uvicorn与websockets为BSD-3-Clause。间接依赖特别保留certifi的MPL-2.0 CA集合说明，以及PSF、Apache与BSD等声明；没有修改或剥离这些包的许可文件。开发工具的vendored代码许可不能只看顶层标签。

| 包 | 版本 | 范围 | 元数据声明 | 检出的许可文件数 |
| --- | --- | --- | --- | --- |
| annotated-doc | 0.0.6 | transitive-runtime | MIT | 1 |
| annotated-types | 0.8.0 | transitive-runtime | MIT | 1 |
| anyio | 4.16.0 | transitive-runtime | MIT | 1 |
| attrs | 26.1.0 | transitive-runtime | MIT | 1 |
| boolean-py | 5.0 | development | BSD-2-Clause | 1 |
| build | 1.6.1 | development | MIT | 1 |
| cachecontrol | 0.14.4 | development | Apache-2.0 | 1 |
| certifi | 2026.10.23 | transitive-runtime | MPL-2.0 | 1 |
| cffi | 2.1.1 | transitive-runtime | MIT-0 | 1 |
| charset-normalizer | 3.5.2 | development | MIT | 1 |
| click | 8.5.1 | transitive-runtime | BSD-3-Clause | 1 |
| cryptography | 50.0.2 | direct-runtime | Apache-2.0 OR BSD-3-Clause | 3 |
| cyclonedx-python-lib | 11.12.0 | development | Apache-2.0 | 2 |
| defusedxml | 0.7.1 | development | PSFL | 1 |
| fastapi | 0.162.7 | direct-runtime | MIT | 1 |
| filelock | 4.2.10 | development | MIT | 1 |
| h11 | 0.16.0 | transitive-runtime | MIT | 1 |
| httpcore | 1.0.9 | transitive-runtime | BSD-3-Clause | 1 |
| httpx | 0.28.1 | transitive-runtime | BSD-3-Clause | 1 |
| httpx-sse | 0.4.3 | transitive-runtime | MIT | 1 |
| idna | 3.20 | transitive-runtime | BSD-3-Clause | 1 |
| iniconfig | 2.3.1 | development | MIT | 1 |
| jsonschema | 4.26.0 | transitive-runtime | MIT | 1 |
| jsonschema-specifications | 2025.9.1 | transitive-runtime | MIT | 1 |
| license-expression | 30.4.4 | development | Apache-2.0 | 2 |
| markdown-it-py | 4.3.0 | development | MIT License | 2 |
| mcp | 1.30.0 | direct-runtime | MIT | 1 |
| mdurl | 0.1.2 | development | MIT License | 1 |
| msgpack | 1.2.4 | development | Apache-2.0 | 1 |
| opentelemetry-api | 1.45.2 | transitive-runtime | Apache-2.0 | 1 |
| packageurl-python | 0.17.6 | development | MIT | 0 |
| packaging | 26.3 | development | Apache-2.0 OR BSD-2-Clause | 3 |
| pip | 26.2.1 | development | MIT | 41 |
| pip-api | 0.0.35 | development | Apache License | 1 |
| pip-audit | 2.10.1 | development | Apache Software License | 1 |
| pip-requirements-parser | 32.0.1 | development | MIT | 0 |
| platformdirs | 4.14.5 | development | MIT | 1 |
| pluggy | 1.7.0 | development | MIT | 1 |
| py-serializable | 2.2.0 | development | Apache-2.0 | 1 |
| pycparser | 3.12 | transitive-runtime | BSD-3-Clause | 1 |
| pydantic | 2.14.3 | transitive-runtime | MIT | 1 |
| pydantic-core | 2.50.4 | transitive-runtime | MIT | 1 |
| pydantic-settings | 2.16.3 | transitive-runtime | MIT | 1 |
| pygments | 2.21.0 | development | BSD-2-Clause | 1 |
| pyjwt | 2.15.1 | transitive-runtime | MIT | 1 |
| pyparsing | 3.3.3 | development | MIT | 1 |
| pyproject-hooks | 1.3.3 | development | MIT | 1 |
| pytest | 9.2.0 | development | MIT | 1 |
| python-dotenv | 1.2.4 | transitive-runtime | BSD-3-Clause | 1 |
| python-multipart | 0.0.33 | transitive-runtime | Apache-2.0 | 1 |
| referencing | 0.37.0 | transitive-runtime | MIT | 1 |
| requests | 2.34.2 | development | Apache-2.0 | 2 |
| rich | 15.0.0 | development | MIT | 1 |
| rpds-py | 2026.9.1 | transitive-runtime | MIT | 1 |
| ruff | 0.17.5 | development | MIT | 1 |
| setuptools | 84.2.1 | development | MIT | 17 |
| sortedcontainers | 2.4.0 | development | Apache 2.0 | 1 |
| sse-starlette | 3.7.0 | transitive-runtime | BSD-3-Clause | 1 |
| starlette | 1.10.0 | transitive-runtime | BSD-3-Clause | 1 |
| tomli | 2.5.0 | development | MIT | 1 |
| tomli-w | 1.2.0 | development | MIT License | 1 |
| typing-extensions | 4.16.0 | transitive-runtime | PSF-2.0 | 1 |
| typing-inspection | 0.4.5 | transitive-runtime | MIT | 1 |
| urllib3 | 2.8.0 | development | MIT | 1 |
| uvicorn | 0.54.0 | direct-runtime | BSD-3-Clause | 1 |
| websockets | 14.2 | direct-runtime | BSD-3-Clause | 1 |

`packageurl-python`在本机安装包中没有由本脚本识别出的许可文件，仅有MIT元数据声明；公开分发前须补核其上游许可证及随包材料。其余间接/开发依赖已生成可复核清单，但未逐行审阅所有条款或所有底层原生库。不得宣称“已完成全部法律合规认证”。

## 项目许可证待定

若希望保持使用和再分发条件简洁，可优先考虑[MIT](https://choosealicense.com/licenses/mit/)；若更重视明确的专利授权条款，可考虑[Apache-2.0](https://choosealicense.com/licenses/apache-2.0/)。最终决定由维护者作出，本轮不创建LICENSE、不替用户授权。无许可证的私人预览仓库不等于已开源。
