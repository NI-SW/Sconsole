---
name: task-planner
description: "任务规划与进度追踪 — 将目标分解为有序任务列表，按序执行并实时追踪完成状态。每完成一个子任务必须立即更新 plan.json。"
version: 1.1.0
author: Sconsole
tags: [sconsole, planning, task-management, workflow]
platforms: [linux]
---

# 任务规划器 (Task Planner)

将用户目标分解为有序任务列表，通过 `plan.json` 文件持久化追踪进度。
**关键原则：每完成一个子任务后，必须立即调用 `plan.py done` 更新状态文件。**

## ⚠️ 执行规则（必须遵守）

当用户提出包含多个步骤的复杂目标时，你必须按以下流程操作：

### 第一步：初始化计划

```bash
python3 /agent/skills/task-planner/scripts/plan.py init "目标" "任务1;任务2;任务3"
```

将目标分解为可独立完成的子任务，用 `;` 分隔。

### 第二步：循环执行（直到全部完成）

```
A. plan.py next          → 获取当前待执行任务
B. 执行该任务（编写代码、运行命令、分析数据等）
C. plan.py done "结果"   → 标记完成，自动显示下一任务
D. 回到 A
```

**绝对不要跳过步骤 C**。每次完成一个子任务后立即标记，不要等到所有任务做完了再统一标记。

### 第三步：汇报结果

```
plan.py report           → 生成汇总报告，展示给用户
```

## 命令速查

| 命令 | 作用 |
|------|------|
| `plan.py init "目标" "任务1;任务2"` | 创建计划，`;` 分隔 |
| `plan.py next` | 显示当前待执行任务 |
| `plan.py done "结果摘要"` | 标记完成 → 自动弹出下一任务 |
| `plan.py skip "原因"` | 跳过当前任务 |
| `plan.py status` | 查看所有任务进度 |
| `plan.py report` | 输出 Markdown 汇总报告 |

## 文件格式

### plan.json

```json
{
  "goal": "目标描述",
  "tasks": [
    {"id": 1, "content": "任务1", "status": "pending", "result": ""},
    {"id": 2, "content": "任务2", "status": "done", "result": "已完成..."}
  ],
  "created_at": "2026-06-04T10:00:00",
  "updated_at": "2026-06-04T10:05:00"
}
```

### 状态值

| 状态 | 含义 |
|------|------|
| `pending` | 待执行 |
| `done` | 已完成 |
| `skipped` | 已跳过 |
| `failed` | 执行失败 |

## 完整示例

> 用户: 帮我分析 data.csv 并生成可视化报告

```
1. plan.py init "分析并可视化" "读取清洗数据;统计分析;生成图表;撰写报告"
2. plan.py next          → [1] 读取清洗数据
3. [执行: 读取 data.csv，处理缺失值...]
4. plan.py done "数据已清洗，1200条有效记录"
5. plan.py next          → [2] 统计分析
6. [执行: 计算均值、方差、分布...]
7. plan.py done "完成统计，均值=42.3，方差=15.7"
8. plan.py next          → [3] 生成图表
9. [执行: matplotlib 生成 3 张图表...]
10. plan.py done "生成 3 张 PNG 图表"
11. plan.py next          → [4] 撰写报告
12. [执行: 整合文字和图表...]
13. plan.py done "报告已生成 → report.md"
14. plan.py report        → 向用户展示最终报告
```

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `PLAN_FILE` | `/agent/volume/plan.json` | 计划文件路径 |
| `AGENT_VOLUME_DIR` | `.` | agent 共享卷路径 |
