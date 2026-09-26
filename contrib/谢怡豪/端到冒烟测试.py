"""端到端冒烟测试驱动：一次性喂入预编排输入，验证完整流程。

仅用于手动验证，非正式交付。运行：python tests/smoke_driver.py

设计思路：开局第一次主菜单立刻保存（不走入战斗，避免随机战斗
回合数不确定导致输入耗尽），从而稳定验证 存档生成 -> 读档继续。
另外用一段带 30 次"攻击"的输入单独验证战斗胜利路径。
"""

import os
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def run(stdin_lines, save_home):
    env = dict(os.environ, PYTHONPATH=ROOT, HOME=save_home)
    proc = subprocess.run(
        [sys.executable, "app.py"],
        input="\n".join(stdin_lines) + "\n",
        capture_output=True,
        text=True,
        env=env,
        cwd=ROOT,
        timeout=30,
    )
    return proc


def grep(text, keys):
    out = []
    for line in text.splitlines():
        if any(k in line for k in keys):
            out.append("  " + line.strip())
    return "\n".join(out) if out else "  (无匹配)"


def main():
    tmp_home = tempfile.mkdtemp()
    save_path = os.path.join(tmp_home, ".dungeon_quest_save.json")
    if os.path.exists(save_path):
        os.remove(save_path)

    # === 验证 1：存档生成 + 读档继续（不进战斗）===
    # 输入：名字 -> 职业 -> 主菜单选 s(保存) -> q(放弃) -> y(确认)
    p1 = run(["勇者Zoe", "战士", "s", "q", "y"], tmp_home)
    print("===== 验证1：存档生成 =====")
    print(grep(p1.stdout, ["欢迎", "💾", "放弃", "已保存"]))
    save_exists = os.path.exists(save_path)
    print("  存档文件存在:", save_exists)

    # === 验证 2：读档继续 + 查看地图 + 背包 ===
    p2 = run(["y", "m", "l", "n", "q", "y"], tmp_home)
    print("\n===== 验证2：读档继续 =====")
    print(grep(p2.stdout, ["继续", "勇者Zoe", "★", "B ", "Lv.", "背包"]))
    print("  存档仍保留:", os.path.exists(save_path))

    # === 验证 3：战斗胜利路径 ===
    # 构造一份存档：玩家在 (0,0)，右侧 (1,0) 放一个怪物房，
    # 读档后向右走必触发战斗。喂入足够攻击以击杀并回到菜单。
    import json
    tmp_home2 = tempfile.mkdtemp()
    save2 = os.path.join(tmp_home2, ".dungeon_quest_save.json")
    grid = [[{"type": "empty" if (x, y) == (0, 0) else
              "monster" if (x, y) == (1, 0) else "empty",
              "cleared": False, "data": {}} for x in range(5)] for y in range(5)]
    save_data = {
        "player": {"name": "勇者Bob", "cls": "战士", "hp": 120, "max_hp": 120,
                    "atk": 14, "defense": 8, "agi": 6, "luk": 4, "gold": 30,
                    "exp": 0, "level": 1, "inventory": {}, "has_star": False},
        "pos": [0, 0], "floor": 1, "grid": grid,
    }
    with open(save2, "w", encoding="utf-8") as f:
        json.dump(save_data, f, ensure_ascii=False)

    p3 = run(["y", "4"] + ["1"] * 40 + ["q", "y"], tmp_home2)
    print("\n===== 验证3：战斗路径 =====")
    print(grep(p3.stdout, ["⚔️", "🏆", "⭐", "💀", "🎉", "升级", "金币"]))
    has_combat = "⚔️" in p3.stdout
    has_win = "🏆" in p3.stdout or "升级" in p3.stdout
    print("  触发过战斗:", has_combat)
    print("  战斗胜利(击杀/升级):", has_win)

    print("\n===== 冒烟测试结束 =====")
    print("退出码:", p1.returncode, p2.returncode, p3.returncode)


if __name__ == "__main__":
    main()
