# 极简使用入门

1. 先从 [CATALOG.zh-CN.md](CATALOG.zh-CN.md) 选一个 Loop。
2. 准备它要求的本地输入文件与权利说明。
3. 初始化：

```bash
python3 scripts/loopctl.py init workflows/名称.json \
  --workspace ./runs/我的任务 \
  --input 输入名=文件路径
```

4. 看下一步：

```bash
python3 scripts/loopctl.py status --workspace ./runs/我的任务
```

5. 让 AI 阅读对应 `skills/名称/SKILL.md` 并执行。每阶段都要登记产物、验证证据，再完成。
6. 中断后重跑 `status`；输入变了用 `change-input`；失败用 `fail`，不要无限重试。
7. 交付前运行：

```bash
python3 scripts/loopctl.py doctor --workspace ./runs/我的任务
python3 scripts/redact_scan.py ./runs/我的任务/20_output
```

注意：本工具包不自动发送、发布、付费、写云端或删除文件。动作清单只是预览。

## 把第一个阶段完整跑通

以下文件全是合成示例，只用于学命令：

```bash
python3 scripts/loopctl.py start preflight --workspace ./my-first-run
cp examples/quickstart/preflight/scope-contract.json ./my-first-run/10_work/
cp examples/quickstart/preflight/rights-ledger.csv ./my-first-run/10_work/
cp examples/quickstart/preflight/review-evidence.md ./my-first-run/10_work/
python3 scripts/loopctl.py record preflight scope_contract ./my-first-run/10_work/scope-contract.json --workspace ./my-first-run
python3 scripts/loopctl.py record preflight rights_ledger ./my-first-run/10_work/rights-ledger.csv --workspace ./my-first-run
```

`preflight` 的三个检查目前需要独立人工证据。对每个检查执行一次：

```bash
python3 scripts/loopctl.py verify preflight required_fields \
  --by human --result pass \
  --evidence ./my-first-run/10_work/review-evidence.md \
  --reviewer demo-reviewer --producer demo-producer \
  --workspace ./my-first-run
```

把 `required_fields` 依次换成 `rights_fail_closed` 和 `untrusted_content_is_data`，三项通过后：

```bash
python3 scripts/loopctl.py complete preflight --workspace ./my-first-run
python3 scripts/loopctl.py status --workspace ./my-first-run
```

真实任务不能复用合成 review 文件；空文件、reviewer 与 producer 相同、旧代产物或验证后被修改的产物都会被阻断。自动检查使用 `--by auto`，结果由 runner 计算，不能自报 PASS。
