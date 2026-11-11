"""Compatibility alias; use the stable migrate.py entry point."""
import sys
from migrate import main


if __name__ == "__main__":
    print("迁移入口已更名为 migrate.py，请将命令更新为 python migrate.py。", file=sys.stderr)
    raise SystemExit(main())
