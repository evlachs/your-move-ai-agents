"""
main.py — точка входа агента RSS-дайджеста
Без флагов запускает планировщик (один раз в день).
С флагом --once выполняет один проход цикла агента и завершается.
"""

import argparse
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def main():
    parser = argparse.ArgumentParser(description='RSS Digest Agent — ежедневный дайджест из RSS-лент')
    parser.add_argument(
        '--once',
        action='store_true',
        help='Выполнить один проход цикла агента и завершиться (без планировщика)',
    )
    args = parser.parse_args()

    if args.once:
        from agent.core import run
        run()
    else:
        from scheduler import start
        start()


if __name__ == '__main__':
    main()
