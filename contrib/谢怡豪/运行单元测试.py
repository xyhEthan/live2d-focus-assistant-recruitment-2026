"""地牢探险 · Dungeon Quest 单元测试。

覆盖核心可测逻辑：伤害计算、受伤、经验升级、物品使用、
地图生成、怪物生成、存档往返。使用 Python 标准库 unittest，
无需额外依赖，运行：``python -m unittest discover -s tests``
"""

import os
import random
import sys
import unittest

# 让测试能导入项目根目录的模块
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import dungeon_game as dg


class TestPlayer(unittest.TestCase):
    def setUp(self):
        self.player = dg.Player(
            name="测试勇者", cls="战士",
            hp=100, max_hp=100, atk=10, defense=5, agi=6, luk=4,
        )

    def test_is_alive(self):
        self.assertTrue(self.player.is_alive())
        self.player.hp = 0
        self.assertFalse(self.player.is_alive())

    def test_attack_damage_positive(self):
        for _ in range(100):
            self.assertGreaterEqual(self.player.attack_damage(), 1)

    def test_take_damage_respects_defense(self):
        self.player.agi = 0  # 关闭闪避
        dmg = self.player.take_damage(20)
        self.assertEqual(dmg, 15)  # 20 - 5 防御
        self.assertEqual(self.player.hp, 85)

    def test_take_damage_minimum_one(self):
        self.player.agi = 0
        dmg = self.player.take_damage(1)  # 极小攻击，至少扣 1
        self.assertEqual(dmg, 1)

    def test_dodge_can_occur(self):
        """高敏捷下应能闪避（统计性断言）。"""
        dodged = False
        p = dg.Player(name="r", cls="盗贼", hp=1000, max_hp=1000,
                      atk=1, defense=0, agi=200, luk=0)
        for _ in range(200):
            p.hp = 1000
            if p.take_damage(50) == 0:
                dodged = True
                break
        self.assertTrue(dodged, "高敏捷应当能闪避至少一次")

    def test_gain_exp_level_up(self):
        msg = self.player.gain_exp(50)  # Lv1 需要 50
        self.assertIsNotNone(msg)
        self.assertEqual(self.player.level, 2)
        self.assertEqual(self.player.exp, 0)
        self.assertEqual(self.player.hp, self.player.max_hp)  # 升级回满

    def test_add_and_use_heal(self):
        self.player.hp = 50
        self.player.add_item("生命药水", 2)
        msg = self.player.use_item("生命药水")
        self.assertIn("恢复", msg)
        self.assertEqual(self.player.hp, 90)
        self.assertEqual(self.player.inventory["生命药水"], 1)

    def test_use_buff_permanent(self):
        self.player.add_item("力量卷轴", 1)
        before = self.player.atk
        self.player.use_item("力量卷轴")
        self.assertEqual(self.player.atk, before + 5)

    def test_use_star_key(self):
        self.player.add_item("星之碎片", 1)
        self.player.use_item("星之碎片")
        self.assertTrue(self.player.has_star)

    def test_use_nonexistent_item(self):
        self.assertEqual(self.player.use_item("生命药水"), "你没有该物品。")


class TestMonster(unittest.TestCase):
    def test_random_monster_scales_with_floor(self):
        random.seed(42)
        low = dg.Monster.random(floor=1)
        high = dg.Monster.random(floor=4)
        # 高楼层至少有一项属性更高（统计性）
        self.assertTrue(high.hp >= low.hp or high.atk >= low.atk)

    def test_attack_damage_positive(self):
        m = dg.Monster("测试怪", 30, 30, 10, 2, 5, 5)
        for _ in range(50):
            self.assertGreaterEqual(m.attack_damage(), 1)


class TestMap(unittest.TestCase):
    def test_generate_map_corners(self):
        grid = dg.generate_map(size=5, seed=1)
        self.assertEqual(len(grid), 5)
        self.assertEqual(grid[0][0].type, "empty")      # 起点
        self.assertEqual(grid[4][4].type, "boss")        # 终点

    def test_generate_map_no_boss_in_middle(self):
        for seed in range(20):
            grid = dg.generate_map(size=5, seed=seed)
            for y in range(5):
                for x in range(5):
                    if (x, y) in [(0, 0), (4, 4)]:
                        continue
                    self.assertNotEqual(grid[y][x].type, "boss")


class TestMovePlayer(unittest.TestCase):
    def test_move_blocked_by_wall(self):
        # 起点 (0,0)，向上/左应被墙挡住
        self.assertEqual(dg.move_player((0, 0), "1", 5), (0, 0))
        self.assertEqual(dg.move_player((0, 0), "3", 5), (0, 0))

    def test_move_within_bounds(self):
        self.assertEqual(dg.move_player((2, 2), "1", 5), (2, 1))
        self.assertEqual(dg.move_player((2, 2), "2", 5), (2, 3))
        self.assertEqual(dg.move_player((2, 2), "3", 5), (1, 2))
        self.assertEqual(dg.move_player((2, 2), "4", 5), (3, 2))

    def test_move_out_of_bounds_blocked(self):
        self.assertEqual(dg.move_player((4, 4), "2", 5), (4, 4))
        self.assertEqual(dg.move_player((4, 4), "4", 5), (4, 4))


class TestSaveLoad(unittest.TestCase):
    def setUp(self):
        self.orig = dg.SAVE_PATH
        dg.SAVE_PATH = os.path.join(os.path.dirname(__file__), ".tmp_save.json")
        if os.path.exists(dg.SAVE_PATH):
            os.remove(dg.SAVE_PATH)

    def tearDown(self):
        if os.path.exists(dg.SAVE_PATH):
            os.remove(dg.SAVE_PATH)
        dg.SAVE_PATH = self.orig

    def test_save_and_load_roundtrip(self):
        player = dg.Player(name="A", cls="战士", hp=70, max_hp=100,
                           atk=10, defense=5, agi=6, luk=4, gold=50, exp=10)
        player.add_item("生命药水", 1)
        grid = dg.generate_map(size=5, seed=3)
        grid[1][1].cleared = True
        dg.save_game(player, (1, 1), 2, grid)

        data = dg.load_game()
        self.assertIsNotNone(data)
        p, pos, floor, g = dg.restore_state(data)
        self.assertEqual(p.name, "A")
        self.assertEqual(p.gold, 50)
        self.assertEqual(p.inventory, {"生命药水": 1})
        self.assertEqual(pos, (1, 1))
        self.assertEqual(floor, 2)
        self.assertTrue(g[1][1].cleared)

    def test_load_missing_save_returns_none(self):
        self.assertIsNone(dg.load_game())

    def test_delete_save(self):
        with open(dg.SAVE_PATH, "w") as f:
            f.write("{}")
        dg.delete_save()
        self.assertFalse(os.path.exists(dg.SAVE_PATH))


if __name__ == "__main__":
    unittest.main()
