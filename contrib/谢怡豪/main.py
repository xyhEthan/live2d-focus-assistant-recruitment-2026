"""地牢探险 · Dungeon Quest —— 一个回合制文字冒险游戏。

本模块实现了完整游戏逻辑：角色创建、随机地牢地图、回合制战斗、
背包系统、商店、陷阱、存档/读档以及胜负判定。所有交互通过标准
输入输出完成，不依赖第三方库。
"""

from __future__ import annotations

import json
import os
import random
import sys
from dataclasses import dataclass, field, asdict
from typing import Optional

# 存档文件路径（放在用户主目录，避免污染项目目录）
SAVE_PATH = os.path.join(os.path.expanduser("~"), ".dungeon_quest_save.json")

# 职业定义：起始属性各有所长，影响游玩策略
CLASSES = {
    "战士": {"hp": 120, "atk": 14, "def": 8, "agi": 6, "luk": 4},
    "法师": {"hp": 80, "atk": 20, "def": 3, "agi": 10, "luk": 8},
    "盗贼": {"hp": 95, "atk": 11, "def": 5, "agi": 14, "luk": 12},
}

# 物品定义：type 决定使用效果
ITEMS = {
    "生命药水": {"type": "heal", "value": 40, "price": 15, "desc": "恢复 40 点生命值"},
    "力量卷轴": {"type": "buff_atk", "value": 5, "price": 25, "desc": "永久提升 5 点攻击力"},
    "铁甲护符": {"type": "buff_def", "value": 4, "price": 25, "desc": "永久提升 4 点防御力"},
    "星之碎片": {"type": "key", "value": 0, "price": 0, "desc": "通关所需的传说圣物"},
}

# 怪物定义：随机出现在怪物房间，强度随楼层提升
MONSTERS = [
    {"name": "哥布林", "hp": 30, "atk": 8, "def": 2, "gold": 12, "exp": 8},
    {"name": "巨型蜘蛛", "hp": 45, "atk": 10, "def": 1, "gold": 18, "exp": 12},
    {"name": "骷髅战士", "hp": 60, "atk": 13, "def": 5, "gold": 25, "exp": 18},
    {"name": "暗影巫师", "hp": 50, "atk": 18, "def": 2, "gold": 35, "exp": 25},
]

# 房间类型权重，用于随机生成地图
ROOM_TYPES = ["empty", "monster", "treasure", "trap", "shop", "rest", "boss"]


@dataclass
class Player:
    name: str
    cls: str
    hp: int
    max_hp: int
    atk: int
    defense: int
    agi: int
    luk: int
    gold: int = 30
    exp: int = 0
    level: int = 1
    inventory: dict = field(default_factory=dict)  # {物品名: 数量}
    has_star: bool = False

    def is_alive(self) -> bool:
        return self.hp > 0

    def attack_damage(self) -> int:
        """计算一次攻击伤害，含暴击判定。"""
        base = self.atk + random.randint(-2, 2)
        crit = random.random() < self.agi / 100.0 * 1.5
        return max(1, int(base * 1.8)) if crit else max(1, base)

    def take_damage(self, raw: int) -> int:
        """承受伤害，含闪避判定，返回实际扣血量。"""
        if random.random() < self.agi / 200.0:
            return 0  # 闪避成功
        dmg = max(1, raw - self.defense)
        self.hp -= dmg
        return dmg

    def gain_exp(self, amount: int) -> Optional[str]:
        """获得经验并处理升级，返回升级提示文本。"""
        self.exp += amount
        need = self.level * 50
        if self.exp >= need:
            self.exp -= need
            self.level += 1
            self.max_hp += 15
            self.hp = self.max_hp  # 升级回满
            self.atk += 3
            self.defense += 2
            return f"⭐ 升级！现在是 Lv.{self.level}，生命上限+15、攻击+3、防御+2，并恢复满血！"
        return None

    def add_item(self, name: str, count: int = 1) -> None:
        self.inventory[name] = self.inventory.get(name, 0) + count

    def use_item(self, name: str) -> str:
        """使用物品，返回结果文本。不存在或类型不匹配时返回提示。"""
        if self.inventory.get(name, 0) <= 0:
            return "你没有该物品。"
        info = ITEMS.get(name)
        if info is None:
            return "未知物品。"
        kind = info["type"]
        val = info["value"]
        if kind == "heal":
            heal = min(val, self.max_hp - self.hp)
            self.hp += heal
            msg = f"恢复 {heal} 点生命值，当前 {self.hp}/{self.max_hp}。"
        elif kind == "buff_atk":
            self.atk += val
            msg = f"攻击力永久 +{val}，当前攻击 {self.atk}。"
        elif kind == "buff_def":
            self.defense += val
            msg = f"防御力永久 +{val}，当前防御 {self.defense}。"
        elif kind == "key":
            self.has_star = True
            msg = "你获得了星之碎片！通关条件之一已达成。"
        else:
            msg = "该物品无法使用。"
        self.inventory[name] -= 1
        if self.inventory[name] <= 0:
            del self.inventory[name]
        return msg


@dataclass
class Monster:
    name: str
    hp: int
    max_hp: int
    atk: int
    defense: int
    gold: int
    exp: int

    @classmethod
    def random(cls, floor: int) -> "Monster":
        base = random.choice(MONSTERS)
        scale = 1 + (floor - 1) * 0.25  # 楼层越高怪物越强
        hp = int(base["hp"] * scale)
        return cls(
            name=base["name"],
            hp=hp,
            max_hp=hp,
            atk=int(base["atk"] * scale),
            defense=int(base["def"] * scale),
            gold=int(base["gold"] * scale),
            exp=int(base["exp"] * scale),
        )

    def attack_damage(self) -> int:
        return max(1, self.atk + random.randint(-1, 2))


@dataclass
class Room:
    type: str
    cleared: bool = False
    data: dict = field(default_factory=dict)


def generate_map(size: int = 5, seed: Optional[int] = None) -> list[list[Room]]:
    """生成 size x size 的地牢地图。起点固定为空房，终点为 Boss 房。"""
    rng = random.Random(seed) if seed is not None else random
    grid: list[list[Room]] = []
    for y in range(size):
        row = []
        for x in range(size):
            # 起点和 Boss 点固定
            if (x, y) == (0, 0):
                row.append(Room("empty"))
            elif (x, y) == (size - 1, size - 1):
                row.append(Room("boss"))
            else:
                # 加权随机，避免 boss 过多
                weights = [3, 5, 3, 3, 2, 2, 0]
                t = rng.choices(ROOM_TYPES, weights=weights, k=1)[0]
                row.append(Room(t))
        grid.append(row)
    return grid


# ----------------------------------------------------------------------------
# 输入辅助
# ----------------------------------------------------------------------------

def prompt(prompt_text: str, valid: Optional[list[str]] = None) -> str:
    """读取一行输入；若给定 valid 则循环直到合法。"""
    while True:
        try:
            line = input(prompt_text).strip()
        except EOFError:
            print("\n检测到输入结束，游戏退出。")
            sys.exit(0)
        if valid is None or line in valid:
            return line
        print("  无效输入，可选：" + " / ".join(valid))


def pause() -> None:
    try:
        input("\n按回车继续...")
    except EOFError:
        sys.exit(0)


# ----------------------------------------------------------------------------
# 战斗
# ----------------------------------------------------------------------------

def combat(player: Player, monster: Monster) -> bool:
    """回合制战斗。返回 True 表示玩家获胜。"""
    print(f"\n⚔️  一只 {monster.name} 出现了！(HP {monster.hp}/{monster.max_hp}, ATK {monster.atk})")
    defending = False
    while player.is_alive() and monster.hp > 0:
        print(f"\n你 HP {player.hp}/{player.max_hp}  |  {monster.name} HP {monster.hp}/{monster.max_hp}")
        action = prompt(
            "动作 [1]攻击 [2]防御 [3]物品 [4]逃跑: ",
            valid=["1", "2", "3", "4"],
        )
        defending = False
        if action == "1":
            dmg = player.attack_damage()
            monster.hp -= dmg
            print(f"  你对 {monster.name} 造成 {dmg} 点伤害！")
        elif action == "2":
            defending = True
            print("  你举起盾牌，本回合受到的伤害减半。")
        elif action == "3":
            if not player.inventory:
                print("  背包是空的，浪费了一回合！")
            else:
                names = list(player.inventory.keys())
                print("  背包：")
                for i, n in enumerate(names, 1):
                    print(f"    [{i}] {n} x{player.inventory[n]} —— {ITEMS[n]['desc']}")
                choice = prompt("  选择物品编号（0 取消）: ")
                if choice != "0" and choice.isdigit() and 1 <= int(choice) <= len(names):
                    msg = player.use_item(names[int(choice) - 1])
                    print("  " + msg)
                else:
                    print("  取消使用。")
        elif action == "4":
            if random.random() < 0.5 + player.agi / 200.0:
                print("  逃跑成功！")
                return False
            print("  逃跑失败！")

        # 怪物反击
        if monster.hp > 0:
            mdmg = monster.attack_damage()
            if defending:
                mdmg = max(1, mdmg // 2)
            actual = player.take_damage(mdmg)
            if actual == 0:
                print(f"  {monster.name} 攻击，但你闪避了！")
            else:
                print(f"  {monster.name} 反击，对你造成 {actual} 点伤害！")

    if not player.is_alive():
        return False
    # 胜利结算
    player.gold += monster.gold
    print(f"\n🏆 击败 {monster.name}！获得 {monster.gold} 金币。")
    up = player.gain_exp(monster.exp)
    if up:
        print(up)
    return True


# ----------------------------------------------------------------------------
# 房间事件
# ----------------------------------------------------------------------------

def enter_room(player: Player, room: Room, floor: int) -> str:
    """处理进入房间的事件，返回房间结果状态文本。"""
    if room.cleared and room.type != "boss":
        return "你回到了这个房间，里面空空如也。"

    if room.type == "empty":
        room.cleared = True
        return "这是一间空荡的房间，什么也没发生。"

    if room.type == "monster":
        m = Monster.random(floor)
        won = combat(player, m)
        room.cleared = True
        if not player.is_alive():
            return "你倒下了..."
        if won:
            return f"怪物房间已肃清。"
        return "你逃离了怪物，房间仍未肃清。"

    if room.type == "treasure":
        # 随机给金币或物品
        if random.random() < 0.5:
            amt = random.randint(15, 40) + player.luk
            player.gold += amt
            print(f"💰 宝箱里有 {amt} 金币！")
        else:
            item = random.choice(["生命药水", "力量卷轴", "铁甲护符"])
            player.add_item(item, 1)
            print(f"🎁 宝箱里有一件【{item}】！")
        room.cleared = True
        return "宝箱已开启。"

    if room.type == "trap":
        dmg = random.randint(8, 18)
        # 盗贼/高敏捷有概率避开
        if random.random() < player.agi / 150.0:
            print("⚠️ 你触发了陷阱，但凭借敏捷躲过了！")
        else:
            player.hp -= dmg
            print(f"🪤 陷阱触发！你受到 {dmg} 点伤害。")
        room.cleared = True
        return "陷阱已被触发。"

    if room.type == "shop":
        print("🏠 一位神秘商人在角落里摆着摊位。")
        shop_loop(player)
        room.cleared = True
        return "你离开了商店。"

    if room.type == "rest":
        heal = player.max_hp // 2
        player.hp = min(player.max_hp, player.hp + heal)
        print(f"🔥 篝火房间，你恢复了 {heal} 点生命值。当前 {player.hp}/{player.max_hp}。")
        room.cleared = True
        return "你休息完毕。"

    if room.type == "boss":
        print("\n👑 你进入了地牢最深处。Boss 房间散发着不祥的气息！")
        boss = Monster("深渊领主", hp=120 + floor * 20, max_hp=120 + floor * 20,
                       atk=18 + floor * 2, defense=6 + floor, gold=200, exp=100)
        won = combat(player, boss)
        room.cleared = True
        if won and not player.has_star:
            print("💫 Boss 被击败，地上散落着星之碎片！")
            player.use_item("星之碎片") if "星之碎片" in player.inventory else None
            player.has_star = True
        return "Boss 房间已肃清。" if won else "你倒在了 Boss 面前..."

    return "未知房间。"


def shop_loop(player: Player) -> None:
    sellable = ["生命药水", "力量卷轴", "铁甲护符"]
    while True:
        print(f"\n  你的金币：{player.gold}")
        print("  货架：")
        for i, n in enumerate(sellable, 1):
            print(f"    [{i}] {n} —— {ITEMS[n]['price']} 金币（{ITEMS[n]['desc']}）")
        print("    [0] 离开商店")
        choice = prompt("  购买编号: ")
        if choice == "0":
            return
        if choice.isdigit() and 1 <= int(choice) <= len(sellable):
            name = sellable[int(choice) - 1]
            price = ITEMS[name]["price"]
            if player.gold >= price:
                player.gold -= price
                player.add_item(name, 1)
                print(f"  购买了 {name}，剩余 {player.gold} 金币。")
            else:
                print("  金币不足！")
        else:
            print("  无效选择。")


# ----------------------------------------------------------------------------
# 存档
# ----------------------------------------------------------------------------

def save_game(player: Player, pos: tuple, floor: int, grid: list) -> None:
    data = {
        "player": asdict(player),
        "pos": list(pos),
        "floor": floor,
        "grid": [[asdict(r) for r in row] for row in grid],
    }
    with open(SAVE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_game() -> Optional[dict]:
    if not os.path.exists(SAVE_PATH):
        return None
    try:
        with open(SAVE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def delete_save() -> None:
    if os.path.exists(SAVE_PATH):
        os.remove(SAVE_PATH)


def restore_state(data: dict) -> tuple:
    p = data["player"]
    player = Player(**p)
    pos = tuple(data["pos"])
    floor = data["floor"]
    grid = [[Room(**cell) for cell in row] for row in data["grid"]]
    return player, pos, floor, grid


# ----------------------------------------------------------------------------
# 主流程
# ----------------------------------------------------------------------------

def create_player() -> Player:
    name = input("输入你的角色名: ").strip() or "勇者"
    print("\n选择职业：")
    for cname, st in CLASSES.items():
        print(f"  {cname}: HP {st['hp']} ATK {st['atk']} DEF {st['def']} "
              f"AGI {st['agi']} LUK {st['luk']}")
    cls = prompt("输入职业名（战士/法师/盗贼）: ", valid=list(CLASSES.keys()))
    st = CLASSES[cls]
    return Player(
        name=name, cls=cls,
        hp=st["hp"], max_hp=st["hp"],
        atk=st["atk"], defense=st["def"],
        agi=st["agi"], luk=st["luk"],
    )


def show_status(player: Player, pos: tuple, floor: int) -> None:
    print("\n" + "=" * 40)
    print(f"{player.name}  Lv.{player.level} {player.cls}  楼层 B{floor}")
    print(f"HP {player.hp}/{player.max_hp}  ATK {player.atk}  DEF {player.defense}  "
          f"AGI {player.agi}  LUK {player.luk}")
    print(f"金币 {player.gold}  经验 {player.exp}/{player.level * 50}")
    inv = ", ".join(f"{k}x{v}" for k, v in player.inventory.items()) or "空"
    print(f"背包: {inv}")
    print(f"坐标: ({pos[0]},{pos[1]})  星之碎片: {'已获得' if player.has_star else '未获得'}")
    print("=" * 40)


def move_player(pos: tuple, direction: str, size: int) -> tuple:
    x, y = pos
    if direction == "1" and y > 0:
        y -= 1
    elif direction == "2" and y < size - 1:
        y += 1
    elif direction == "3" and x > 0:
        x -= 1
    elif direction == "4" and x < size - 1:
        x += 1
    else:
        print("那边是墙壁，无法通过。")
    return (x, y)


def main_loop() -> None:
    print("=" * 50)
    print("        地牢探险 · Dungeon Quest")
    print("=" * 50)
    print("你是受雇前来寻找「星之碎片」的冒险者。深入地牢，击败深渊领主，")
    print("夺回星之碎片并找到通往下一层的楼梯。\n")

    player = None
    pos = (0, 0)
    floor = 1
    grid = None

    # 读取存档
    data = load_game()
    if data:
        ans = prompt("检测到存档，是否继续？(y/n): ", valid=["y", "n"])
        if ans == "y":
            player, pos, floor, grid = restore_state(data)

    if player is None:
        player = create_player()
        grid = generate_map(size=5, seed=random.randint(0, 99999))
        print(f"\n欢迎，{player.name}！你站在地牢 B{floor} 的入口。")

    size = len(grid)
    visited_exit = False

    while player.is_alive():
        show_status(player, pos, floor)
        room = grid[pos[1]][pos[0]]

        # 进入未清理房间时触发事件
        if not room.cleared or room.type == "boss":
            print(f"\n🚪 你进入了一个【{room.type}】房间。")
            result = enter_room(player, room, floor)
            print(result)
            if not player.is_alive():
                break

        # 通关判定：拥有星之碎片且击败 boss
        if room.type == "boss" and room.cleared and player.has_star:
            print(f"\n🎉 恭喜！{player.name} 夺回了星之碎片，拯救了王国！")
            print(f"最终状态：Lv.{player.level}，金币 {player.gold}。")
            delete_save()
            visited_exit = True
            break

        # 移动 / 操作菜单
        print("\n移动: [1]上 [2]下 [3]左 [4]右")
        print("其他: [s]保存 [l]查看背包 [m]查看地图 [q]放弃")
        action = prompt("选择: ", valid=["1", "2", "3", "4", "s", "l", "m", "q"])

        if action == "q":
            if prompt("确定放弃这次冒险？(y/n): ", valid=["y", "n"]) == "y":
                print("你黯然离去了。存档保留。")
                save_game(player, pos, floor, grid)
                visited_exit = True
                break
        elif action == "s":
            save_game(player, pos, floor, grid)
            print("💾 进度已保存。")
        elif action == "l":
            if not player.inventory:
                print("背包是空的。")
            else:
                for n, c in player.inventory.items():
                    print(f"  {n} x{c} —— {ITEMS[n]['desc']}")
                if prompt("是否使用物品？(y/n): ", valid=["y", "n"]) == "y":
                    names = list(player.inventory.keys())
                    for i, n in enumerate(names, 1):
                        print(f"  [{i}] {n}")
                    c = prompt("选择编号: ")
                    if c.isdigit() and 1 <= int(c) <= len(names):
                        print(player.use_item(names[int(c) - 1]))
        elif action == "m":
            print("\n地图（? 未探索，. 已清理，B Boss，★ 你的位置）：")
            for y in range(size):
                row_str = ""
                for x in range(size):
                    if (x, y) == pos:
                        row_str += "★ "
                    elif grid[y][x].type == "boss":
                        row_str += "B "
                    elif grid[y][x].cleared:
                        row_str += ". "
                    else:
                        row_str += "? "
                print("  " + row_str)
        else:
            # 移动
            new_pos = move_player(pos, action, size)
            if new_pos != pos:
                pos = new_pos

    if not visited_exit and not player.is_alive():
        print(f"\n💀 {player.name} 倒在了地牢深处...游戏结束。")
        delete_save()


def main() -> None:
    try:
        main_loop()
    except KeyboardInterrupt:
        print("\n\n游戏被中断。再见！")


if __name__ == "__main__":
    main()
