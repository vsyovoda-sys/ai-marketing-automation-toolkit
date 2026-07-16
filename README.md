# AI 营销自动化 Loop 工具包

给营销传播、自媒体创作者、产品 GTM 与办公者使用的 10 个端到端 AI Loop。它不是提示词合集：每个 Loop 都有输入契约、阶段状态、人工关口、失败预算、产物证据和发布前检查。

## 3 分钟开始

无需安装第三方 Python 包。

```bash
python3 scripts/validate_workflow.py workflows/*.json
python3 scripts/loopctl.py init workflows/research-to-brief.json \
  --workspace ./my-first-run \
  --input research_request=./examples/quickstart/research-request.md \
  --input source_manifest=./examples/quickstart/source-manifest.csv
python3 scripts/loopctl.py status --workspace ./my-first-run
```

接下来让 AI 读取对应 `skills/*/SKILL.md`，按 `status` 显示的可开始阶段执行。所有产物写入运行目录；中断后再次运行 `status` 即可继续。

## 先选哪个

| 需求 | 使用 |
|---|---|
| 先判断我是采购创作者，还是寻找自己/产品的平台位置 | `creator-strategy-router` |
| 多源调研、事实核验、Brief | `research-to-brief` |
| 品牌/代理商已有授权采购入口，要筛选创作者、做采买组合和预算 | `creator-portfolio` |
| 个人创作者、AI IP、艺人团队或产品要找平台定位与内容实验 | `platform-positioning-benchmark` |
| Campaign 从 Brief 到上线包 | `campaign-ops` |
| 产品定位、卖点、渠道小实验 | `product-gtm` |
| 一份材料改写成多平台内容 | `content-repurpose` |
| 长音视频、字幕、人工选段、渲染 QA | `media-production` |
| 邮件/会议/聊天导出变行动台 | `office-action-desk` |
| KPI 监测、异常与原因诊断 | `kpi-monitor-diagnose` |

完整对照见 [CATALOG.zh-CN.md](CATALOG.zh-CN.md)，更短的命令说明见 [QUICKSTART.zh-CN.md](QUICKSTART.zh-CN.md)。
四类人群怎样组合现有 Loop，见 [docs/四类人群组合场景.md](docs/四类人群组合场景.md)。
平台创作者战略的入口与证据边界见 [docs/平台创作者战略架构.md](docs/平台创作者战略架构.md)。
官方备案原文遇到空白预览时，先读 [docs/平台机制证据阅读说明.md](docs/平台机制证据阅读说明.md)。

## 默认安全边界

- 本地优先、只读优先；首版不接真实账号。
- 外发、发布、付费、云端写入只生成 `plan_only` 动作清单，不执行。
- AI 不能批准自己的产物；人工阶段需要独立记录。
- 不绕过登录、验证码、访问控制、API scope 或平台频率限制。
- 不删除用户文件；整理工具只生成计划和复制归档。
- 发布物从允许字段重建，并对秘密、身份线索、路径和未知格式 fail-closed。

安全模型见 [SECURITY.md](SECURITY.md)，隐私与权利字段见 [PRIVACY.md](PRIVACY.md)。

## 共用脚本

- `loopctl.py`：typed DAG、事件日志、中断恢复、有限重试、输入变化失效。
- `validate_workflow.py`：验证工作流契约。
- `data_quality.py`：CSV 质量画像和重复候选。
- `redact_scan.py`：不回显命中值的敏感扫描。
- `release_gate.py`：按允许清单从空目录重建发布物。
- `action_manifest.py`：只生成外部动作预览。
- `safe_curator.py`：非删除式本机整理和候选归档。

## 方法来源

工具包从真实项目里的成功链路、聊天中未沉淀的优化、失败恢复三条线抽象而来，并用高采用度开源项目的方法做了补强。第三方 URL、Star 快照、许可证与具体借鉴点见 [docs/开源方法来源.md](docs/开源方法来源.md)。本仓库没有复制这些项目的源码。

## 验证

```bash
python3 -m unittest discover -s tests -v
for skill in skills/*; do python3 /path/to/skill-creator/scripts/quick_validate.py "$skill"; done
python3 scripts/redact_scan.py . --report ./redaction-report.json
```

敏感扫描器对未知二进制格式默认阻断；媒体和图片发布还需要 OCR、元数据与人工复核。

## 许可

本工具包采用 [MIT License](LICENSE)。引用的第三方项目保留各自许可证。
