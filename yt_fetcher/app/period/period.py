from datetime import date, datetime

# from calendar import monthrange
import re

DATETIME_YT_F = "%Y-%m-%dT%H:%M:%SZ"
DATE_REGEX = re.compile(
    r"((?P<year1>\d{4})[-/.](?P<month1>\d{1,2}))|(?P<month2>\d{1,2})[-/.](?P<year2>\d{4})"
)


class Period(date):
    def __new__(cls, month: int = date.today().month, year: int = date.today().year):
        return super().__new__(cls, year, month, 1)

    def __str__(self) -> str:
        return self.strftime("%Y-%m-%d")

    def strf(self, format="%Y-%m-%d") -> str:
        if format == "%p":
            return self.strftime("%Y-%m")
        return self.strftime(format)

    def next(self, months: int = 1):
        total_months = self.month + months
        new_year = self.year + (total_months - 1) // 12
        new_month = (total_months - 1) % 12 + 1
        return Period(new_month, new_year)

    def as_range(self, months: int = 1) -> tuple:
        res = (self, self.next(months))
        return res if months > 0 else res[::-1]

    @classmethod
    def parse(cls, s: str | datetime):
        if isinstance(s, str):
            match = DATE_REGEX.search(s)
            if match:
                if match.group("year1"):  # Формат YYYY-MM
                    year = match.group("year1")
                    month = match.group("month1")
                else:  # Формат DD.MM.YYYY
                    year = match.group("year2")
                    month = match.group("month2")

                return Period(int(month), int(year))
            raise ValueError("Неверный формат даты")
        else:
            return Period(s.month, s.year)


# Tests
# period = Period()
# print(period)  # Выводит текущий месяц и год в формате YYYY-MM
# print(period.next(3))  # Сдвинет дату на 3 месяца вперед
# print(period.next(-1))
# print(period.next(-12))
# print(period.as_range())  # Вернет диапазон на 1 месяц
# print(period.as_range(-3))  # Вернет диапазон на 3 месяца


# strings = ["2024-3-1", "2024-05", "1.5.2024"]
# for string in strings:
#     print(
#         f"Строка {string} преобразована в период {Period.parse(string)}"
#     )
