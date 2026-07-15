# Loop 清单

| Loop | 最适合谁 | 完整解决什么 | 主要输入 | 主要输出 |
|---|---|---|---|---|
| `research-to-brief` | 四类人群 | 多源资料→声明台账→冲突→Brief→独立审查 | 研究问题、来源/权利清单 | 声明台账、Brief、审查记录 |
| `creator-portfolio` | 营销/PR/GTM | 合规数据→质量→匹配→校准→预算组合 | 目标预算、候选 CSV、数据许可 | 特征表、评分契约、组合方案 |
| `campaign-ops` | 营销全链路 | Brief→KPI→策略→工作包→就绪→上线包 | Brief、资源契约、证据包 | 策略、责任矩阵、上线决策包 |
| `product-gtm` | 软件/硬件产品与市场 | 产品证据→定位/主张→渠道小实验 | 产品证据、市场请求 | 定位包、声明矩阵、实验契约 |
| `content-repurpose` | 创作者/新媒体 | 可信材料→主稿→平台变体→人审→规则提案 | 源材料、内容 Brief、权利清单 | 主稿、平台包、编辑差异规则 |
| `media-production` | 创作者/内容团队 | 转写→时间线→人工选段→字幕/渲染→目视 QA | 媒体清单、剪辑 Brief | 时间线、字幕、成片或明确降级物 |
| `office-action-desk` | 办公者/项目经理 | 本地导出→行动/决策/风险→草稿→动作预览 | 明确组织与来源、本地导出 | 行动台、草稿、plan-only 清单 |
| `kpi-monitor-diagnose` | 四类人群 | 指标契约→数据质检→异常→多假设诊断 | 指标定义、指标 CSV | 异常表、诊断、决策读数 |

## 共用底座不是业务 Loop

- `loopctl.py`：保证流程能停、能续、能审计。
- `data_quality.py`：负责可复现数据检查，不替业务做评分判断。
- `action_manifest.py`：只写动作预览，不接真实账号。
- `redact_scan.py` + `release_gate.py`：构成发布阻断门。
- `safe_curator.py`：整理本机但不移动/删除原文件。

## 选择规则

- 只是需要一段文案：先补源材料与声明证据，再用 `content-repurpose`；不要把一句提示词叫自动化。
- 需要跨多个 Loop：用 `campaign-ops` 做编排，但每个子 Loop 必须交付自己的验证证据。
- 需要真实发送/发布/写回：先停在 action manifest；真实连接器需另做租户、幂等、权限和 shadow-mode 审查。
