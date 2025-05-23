import csv
import json
import logging
from datetime import datetime, UTC
from logging.handlers import RotatingFileHandler
from pythonjsonlogger import jsonlogger

from app.config import settings


def setup_logger():
    logger = logging.getLogger("ytr")
    logger.setLevel(settings.LOG_LEVEL)

    # Форматтер для логов
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

    # Хендлер для файла с ротацией (10MB максимум, 5 бэкапов)
    file_handler = RotatingFileHandler(
        "logs/yt_fetcher.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",  # Добавляем явное указание кодировки UTF-8
    )
    file_handler.setFormatter(formatter)

    # Хендлер для консоли
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


logger = setup_logger()


# logger = logging.getLogger()

# logHandler = logging.StreamHandler()


class CustomJsonFormatter(jsonlogger.JsonFormatter):
    def add_fields(self, log_record, record, message_dict):
        super(CustomJsonFormatter, self).add_fields(log_record, record, message_dict)
        if not log_record.get("timestamp"):
            now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
            log_record["timestamp"] = now
        if log_record.get("level"):
            log_record["level"] = log_record["level"].upper()
        else:
            log_record["level"] = record.levelname


# formatter = CustomJsonFormatter(
#     "%(timestamp)s %(level)s %(message)s %(module)s %(funcName)s"
# )


# logHandler.setFormatter(formatter)
# logger.addHandler(logHandler)
# logger.setLevel(settings.LOG_LEVEL)

# logger.debug("Debug message")
# logger.info("Info message")
# logger.error("Error message", extra={"table": "tt"}, exc_info=True)


#####################################
# Some function to save log data
#####################################


def print_json(j):
    formatted_json = json.dumps(j, indent=2, default=str, ensure_ascii=False)
    print(formatted_json)


def save_json(data_json, filename: str = "out_json.txt"):
    with open(filename, "w", encoding="utf-8") as json_file:
        json.dump(data_json, json_file, indent=2, default=str, ensure_ascii=False)


def save_json_csv(data_json, filename: str):
    # Сохраняем данные в CSV файл с табуляцией в качестве разделителя
    fieldnames = data_json[0].keys()

    with open(filename, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        writer.writerows(data_json)


def save_errors(errors, type: str):
    filename = (
        "logs/" + datetime.now().strftime("%Y-%m-%d-%H-%M-%S") + f"_{type}_errors_.csv"
    )
    if isinstance(errors, str):
        with open(filename, "w", encoding="utf-8") as file:
            file.write(errors)
        return True
    try:
        save_json_csv(errors, filename)
    except Exception as e:
        with open(filename, "w", encoding="utf-8") as file:
            file.write(str(errors))
    return True


#####################################
