"""
兼容入口：保留旧入口名，内部转发到现代化主界面。
"""

from heytea_modern import ModernDrawingApp, ctk


def main():
    root = ctk.CTk()
    app = ModernDrawingApp(root)
    root.mainloop()
    return app


if __name__ == "__main__":
    main()
