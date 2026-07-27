"""
main.py — точка входа агента мониторинга вакансий
Без флагов запускает планировщик (проверка HH.ru каждые N часов).
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
    parser = argparse.ArgumentParser(description='Vacancy Tracker Agent — мониторинг вакансий на HH.ru')
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
