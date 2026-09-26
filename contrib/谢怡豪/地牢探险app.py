"""地牢探险 · Dungeon Quest —— 入口文件。

直接运行本文件即可开始游戏。游戏逻辑全部封装在
``main`` 模块中，本文件只负责启动，便于被贡献项目的
统一入口规范所识别（仓库根目录的 app.py）。
"""

from tkinter import Y

from main import main


if __name__ == "__main__":
    main()