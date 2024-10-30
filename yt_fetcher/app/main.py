import os
import sys

sys.path.append(os.getcwd())

from app.services import *
from app.period import Period

# print("Текущая рабочая папка:", os.getcwd())


def main():
    update_data_for_period(category_id=6, period=Period())


if __name__ == "__main__":

    # print(os.path.realpath(__file__))
    # print(os.path.dirname(__file__))
    # print(os.pardir)
    # sys.path.append(
    #     os.path.join(os.path.dirname(os.path.realpath(__file__)), os.pardir)
    # )
    main()
