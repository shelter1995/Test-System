# Skill规范化一键生成

## 一键命令

在项目根目录执行：

```bash
generate_skill_outputs.bat
```

执行内容：

1. 读取 `skill_pipeline_config.json`
2. 调用 `run_skill_compliance_suite.py`
3. 自动生成：
   - 方案（SCQA+MECE+营销话术）
   - 培训讲义
   - 测试题（含答案速查表）
   - README
4. 自动自检并输出 JSON 报告

## 结果报告

每次执行都会覆盖：

`training_output/_skill_pipeline_last_report.json`

- `ok=true`：本次生成与自检通过
- `ok=false`：有不符合项，查看 `validation` 字段
- `attempt`：本次通过时使用的重试次数

## 可调参数

编辑 `skill_pipeline_config.json`：

- `database`
- `client_unit`
- `listener_role`
- `relation`
- `audience`
- `training_duration`
- `question_count`
- `timeout`
- `max_attempts`（生成波动时自动重试次数，建议 2-3）
