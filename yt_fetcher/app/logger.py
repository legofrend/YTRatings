import csv
import json
import logging
from datetime import datetime, UTC
from pythonjsonlogger import jsonlogger

from app.config import settings


logger = logging.getLogger()

logHandler = logging.StreamHandler()

#####################################
# Some function to save log data
#####################################


def print_json(j):
    formatted_json = json.dumps(j, indent=2, default=str, ensure_ascii=False)
    print(formatted_json)


def save_json(data_json, filename: str = "out_json.txt"):
    with open(filename, "w", encoding="utf-8") as json_file:
        json.dump(data_json, json_file, indent=2, default=str, ensure_ascii=False)


def save_df(df_data, filename: str = "out.csv"):
    df_data.to_csv(filename, index=False, sep="\t", decimal=",")


def save_json_csv(data_json, filename: str):
    # Сохраняем данные в CSV файл с табуляцией в качестве разделителя
    fieldnames = data_json[0].keys()

    with open(filename, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        writer.writerows(data_json)


def save_errors(errors, type: str):
    filename = (
        "logs/" + datetime.now().strftime("%Y-%m-%d-%H-%M-%S") + f"{type}_errors_.csv"
    )
    save_json_csv(errors, filename)


#####################################


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


formatter = CustomJsonFormatter(
    "%(timestamp)s %(level)s %(message)s %(module)s %(funcName)s"
)

logHandler.setFormatter(formatter)
logger.addHandler(logHandler)
logger.setLevel(settings.LOG_LEVEL)

# logger.debug("Debug message")
# logger.info("Info message")
# logger.error("Error message", extra={"table": "tt"}, exc_info=True)
