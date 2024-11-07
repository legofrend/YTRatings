from datetime import date, datetime
import re

DATETIME_YT_F = "%Y-%m-%dT%H:%M:%SZ"
DATE_REGEX = re.compile(
    r"((?P<year1>\d{4})[-/.](?P<month1>\d{1,2}))|(?P<month2>\d{1,2})[-/.](?P<year2>\d{4})"
)


class Period:
    def __init__(self, month: int = date.today().month, year: int = date.today().year):
        self._date = date(year, month, 1)

    def __str__(self) -> str:
        return self._date.strftime("%Y-%m")

    def next(self, months: int = 1):
        total_months = self._date.month + months
        n_year = self._date.year + (total_months - 1) // 12
        n_month = (total_months - 1) % 12 + 1
        return Period(n_month, n_year)

    def as_range(self, months: int = 1):
        res = [self._date, self.next(months)._date]
        return res if months > 0 else res[::-1]

    def strf(self, format="%Y-%m-%d"):
        return self._date.strftime(format)

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


class Period_old:
    _num: int
    _m: int
    _y: int

    def __init__(
        self,
        month: int = date.today().month,
        year: int = date.today().year,
        _num: int = "",
    ):
        if _num:
            month = _num % 12
            year = _num // 12

        if year < 100:
            year += 2000
        self._num = year * 12 + month
        self._m = month
        self._y = year

    def __repr__(self):
        return f"{self._y}-{self._m:02}"

    def month(self):
        return self._m

    def year(self):
        return self._y

    def next(self, months: int = 1):
        return Period(_num=self._num + months)

    def as_dt(self):
        return date(year=self._y, month=self._m, day=1)

    def as_str(self, full: bool = False):
        return f"{self._y}-{self._m:02}" + ("-01" if full else "")

    def as_period(self):
        return self._num

    def as_dt_range(self):
        return [
            self.as_dt(),
            (
                self.as_dt().replace(month=self._m + 1)
                if self._m < 12
                else self.as_dt().replace(year=self._y + 1, month=1)
            ),
        ]

    def as_yt_str(self):
        return self.as_dt().strftime(DATETIME_YT_F)

    def as_yt_range(self):
        r = self.as_dt_range()
        return [r[0].strftime(DATETIME_YT_F), r[1].strftime(DATETIME_YT_F)]

    def parse(self, s: str | datetime):
        if isinstance(s, str):
            return self.parse_str(s)

        self._y = s.year
        self._m = s.month
        self._num = self._y * 12 + self._m
        return self

    def parse_str(self, s: str):

        match = DATE_REGEX.search(s)
        if match:
            if match.group("year1"):  # Формат YYYY-MM
                year = match.group("year1")
                month = match.group("month1")
            else:  # Формат DD.MM.YYYY
                year = match.group("year2")
                month = match.group("month2")

            self._y = int(year)
            self._m = int(month)
            self._num = self._y * 12 + self._m
            return self

        raise ValueError("Неверный формат даты")


# period = Period()
# print(period)  # Выводит текущий месяц и год в формате YYYY-MM
# print(period.next(3))  # Сдвинет дату на 3 месяца вперед
# print(period.next(-1))
# print(period.next(-12))
# print(period.as_range())  # Вернет диапазон на 3 месяца
# print(period.as_range(-3))  # Вернет диапазон на 3 месяца


# strings = ["2024-3-1", "2024-05", "1.5.2024"]
# for string in strings:
#     print(f"Строка {string} преобразована в период {per.parse(string)}") # per.parse(string)
