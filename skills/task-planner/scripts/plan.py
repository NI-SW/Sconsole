#!/usr/bin/env python3
"""
Sconsole Task Planner — 任务规划与进度追踪

用法:
  plan.py init "<目标>" "<任务1>;<任务2>;..."
      创建计划文件，将多个任务用 ; 分隔

  plan.py next
      显示当前待执行的任务

  plan.py done [结果描述]
      标记当前任务为完成，自动进入下一任务

  plan.py status
      查看所有任务的完成状态

  plan.py report
      生成最终汇总报告

计划文件保存在 /agent/volume/plan.json（容器内）或当前工作目录。
环境变量 PLAN_FILE 可覆盖路径。
"""
import os
import sys
import json
from datetime import datetime

PLAN_FILE = os.getenv("PLAN_FILE", os.path.join(os.getenv("AGENT_VOLUME_DIR", "."), "plan.json"))


def load_plan():
    if not os.path.exists(PLAN_FILE):
        print(f"ERROR: 计划文件不存在: {PLAN_FILE}")
        print("请先使用 'init' 命令创建计划")
        sys.exit(1)
    with open(PLAN_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_plan(plan):
    with open(PLAN_FILE, "w", encoding="utf-8") as f:
        json.dump(plan, f, indent=2, ensure_ascii=False)
    print(f"计划已保存: {PLAN_FILE}")


def find_current(plan):
    """找到第一个状态为 pending 的任务"""
    for i, t in enumerate(plan["tasks"]):
        if t["status"] == "pending":
            return i
    return -1


def cmd_init(goal, tasks_str):
    """创建计划文件"""
    if os.path.exists(PLAN_FILE):
        existing = load_plan()
        has_pending = any(t["status"] == "pending" for t in existing["tasks"])
        if has_pending:
            print(f"WARNING: 已有未完成的计划，将被覆盖:")
            cmd_status()
            print()

    tasks = [{"id": i + 1, "content": t.strip(), "status": "pending", "result": ""}
             for i, t in enumerate(tasks_str.split(";")) if t.strip()]

    if not tasks:
        print("ERROR: 至少需要一个任务")
        sys.exit(1)

    plan = {
        "goal": goal.strip(),
        "tasks": tasks,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
    }
    save_plan(plan)

    print(f"📋 计划已创建 — {len(tasks)} 个任务")
    for t in tasks:
        print(f"  [{t['id']}] [ ] {t['content']}")
    print(f"\n📌 开始执行: [1] {tasks[0]['content']}")


def cmd_next():
    """显示当前待执行任务"""
    plan = load_plan()
    idx = find_current(plan)
    if idx < 0:
        print("✅ 所有任务已完成！使用 'report' 查看汇总。")
        return

    t = plan["tasks"][idx]
    done = sum(1 for t2 in plan["tasks"] if t2["status"] == "done")
    total = len(plan["tasks"])
    print(f"📌 当前任务 ({done}/{total}): [{t['id']}] {t['content']}")


def cmd_done(result=""):
    """标记当前任务完成"""
    plan = load_plan()
    idx = find_current(plan)
    if idx < 0:
        print("✅ 所有任务已完成！使用 'report' 查看汇总。")
        return

    t = plan["tasks"][idx]
    t["status"] = "done"
    t["result"] = result.strip() if result else "完成"
    plan["updated_at"] = datetime.now().isoformat()
    save_plan(plan)

    done = sum(1 for t2 in plan["tasks"] if t2["status"] == "done")
    total = len(plan["tasks"])
    print(f"✅ [{t['id']}] {t['content']} — 完成 ({done}/{total})")

    nxt = find_current(plan)
    if nxt >= 0:
        nt = plan["tasks"][nxt]
        print(f"📌 下一任务: [{nt['id']}] {nt['content']}")
    else:
        print("🎉 全部任务完成！使用 'report' 查看汇总报告。")


def cmd_status():
    """查看状态"""
    plan = load_plan()
    done = sum(1 for t in plan["tasks"] if t["status"] == "done")
    total = len(plan["tasks"])

    print(f"📋 目标: {plan['goal']}")
    print(f"📊 进度: {done}/{total}")
    print()

    for t in plan["tasks"]:
        icon = "✅" if t["status"] == "done" else "⬜" if t["status"] == "pending" else "❌"
        print(f"  [{t['id']}] {icon} {t['content']}")
        if t["result"]:
            print(f"       ↳ {t['result'][:80]}")


def cmd_report():
    """生成汇总"""
    plan = load_plan()
    done = sum(1 for t in plan["tasks"] if t["status"] == "done")
    total = len(plan["tasks"])
    all_done = done == total

    lines = []
    lines.append(f"## 任务执行报告")
    lines.append(f"")
    lines.append(f"**目标**: {plan['goal']}")
    lines.append(f"**状态**: {'✅ 全部完成' if all_done else f'进行中 ({done}/{total})'}")
    lines.append(f"**创建时间**: {plan['created_at'][:19]}")
    lines.append(f"**更新时间**: {plan['updated_at'][:19]}")
    lines.append(f"")
    lines.append(f"### 任务明细")
    lines.append(f"")
    for t in plan["tasks"]:
        icon = "✅" if t["status"] == "done" else "⬜"
        lines.append(f"- {icon} **{t['content']}**")
        if t["result"] and t["result"] != "完成":
            lines.append(f"  - {t['result']}")
    lines.append(f"")

    report = "\n".join(lines)
    print(report)

    # 同时写入报告文件
    report_file = PLAN_FILE.replace(".json", "_report.md")
    with open(report_file, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"📄 报告已保存: {report_file}")


def cmd_skip(reason=""):
    """跳过当前任务"""
    plan = load_plan()
    idx = find_current(plan)
    if idx < 0:
        print("✅ 所有任务已完成。")
        return

    t = plan["tasks"][idx]
    t["status"] = "skipped"
    t["result"] = f"跳过: {reason}" if reason else "跳过"
    plan["updated_at"] = datetime.now().isoformat()
    save_plan(plan)

    print(f"⏭ [{t['id']}] {t['content']} — 已跳过")

    nxt = find_current(plan)
    if nxt >= 0:
        nt = plan["tasks"][nxt]
        print(f"📌 下一任务: [{nt['id']}] {nt['content']}")
    else:
        print("🎉 全部任务完成！")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "init":
        if len(sys.argv) < 4:
            print("用法: plan.py init \"目标\" \"任务1;任务2;...\"")
            sys.exit(1)
        cmd_init(sys.argv[2], sys.argv[3])

    elif cmd == "next":
        cmd_next()

    elif cmd == "done":
        result = sys.argv[2] if len(sys.argv) > 2 else ""
        cmd_done(result)

    elif cmd == "status":
        cmd_status()

    elif cmd == "report":
        cmd_report()

    elif cmd == "skip":
        reason = sys.argv[2] if len(sys.argv) > 2 else ""
        cmd_skip(reason)

    else:
        print(f"未知命令: {cmd}")
        print(__doc__)
        sys.exit(1)
