"""
AI Chat 桌面宠物 - 主入口文件
模块化架构 - 简洁的启动器
"""
import sys

import live2d.v3 as live2d
from PySide6.QtWidgets import QApplication

from src.ui import DesktopPetWindow


def main():
    """主函数 - 启动应用程序"""
    # 1. 初始化 Live2D 底层库
    live2d.init()
    
    # 2. 创建 Qt 应用
    app = QApplication(sys.argv)
    
    # 3. 创建并显示主窗口
    window = DesktopPetWindow()
    window.show()
    
    # 4. 运行事件循环
    exit_code = app.exec()
    
    # 5. 清理资源
    live2d.dispose()
    
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
