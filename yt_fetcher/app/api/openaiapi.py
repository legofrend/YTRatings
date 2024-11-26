from typing import Literal
from openai import OpenAI
import json
from app.config import settings
from app.logger import logger, save_errors

client = OpenAI(
    api_key=settings.OAI_API_KEY,
)

MODELS = Literal[
    "gpt-4-1106-preview",
    "o1-preview",
    "gpt-4",
    "o1-preview-2024-09-12",
    "gpt-4o-2024-11-20",
    "o1-mini-2024-09-12",
    "dall-e-2",
    "o1-mini",
    "chatgpt-4o-latest",
    "gpt-3.5-turbo",
    "gpt-3.5-turbo-0125",
    "babbage-002",
    "gpt-4-turbo-2024-04-09",
    "davinci-002",
    "dall-e-3",
    "text-embedding-3-large",
    "gpt-3.5-turbo-16k",
    "tts-1-hd-1106",
    "gpt-4-turbo-preview",
    "gpt-4-turbo",
    "text-embedding-ada-002",
    "gpt-4o-mini-2024-07-18",
    "gpt-4-0613",
    "gpt-4o-mini",
    "text-embedding-3-small",
    "tts-1-hd",
    "gpt-4o",
    "gpt-4o-2024-08-06",
    "gpt-3.5-turbo-1106",
    "gpt-3.5-turbo-instruct",
    "gpt-4o-audio-preview",
    "whisper-1",
    "gpt-4o-audio-preview-2024-10-01",
    "gpt-4-0125-preview",
    "gpt-4o-realtime-preview",
    "tts-1",
    "tts-1-1106",
    "gpt-3.5-turbo-instruct-0914",
    "gpt-4o-2024-05-13",
    "gpt-4o-realtime-preview-2024-10-01",
]
# https://openai.com/api/pricing/
# gpt-4o-mini
# $0.150 / 1M input tokens
# $0.600 / 1M output tokens
# example: 10 titles = 1K tokens total, 100 titles avg monthly per channel = 10K tokens * 0.6/1000 = $0.006 = 0.6 RUB


# Функция для отправки запроса к ChatGPT
def chat_with_gpt(
    prompt: str,
    model: MODELS = "gpt-4o-mini",
    temperature: float = 0.7,
    is_json: bool = False,
):
    response = client.chat.completions.create(
        messages=[
            {
                "role": "user",
                "content": prompt,
            }
        ],
        model=model,
        max_tokens=15000,  # Максимальное количество токенов в ответе
        temperature=temperature,  # Креативность (от 0 до 1)
    )
    logger.info("Total tokens: " + str(response.usage.total_tokens))

    content = response.choices[0].message.content
    # save_errors(content, "ai_resp")
    if is_json:
        try:
            content_json = json.loads(content)
            return content_json
        except Exception as e:
            logger.error("Can't parse content to JSON: " + str(e))
            save_errors(content, "ai_resp")
            return None
    return content
