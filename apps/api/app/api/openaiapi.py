from typing import Literal
from openai import OpenAI
import json
from app.config import settings
from app.logger import logger, save_errors
import os

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
    file_prompt: str = None,
    model: MODELS = "gpt-4o-mini",
    temperature: float = 0.7,
    is_json: bool = False,
    data: list = None,
    limit: int = 10,
):
    responses = []

    # Prepare base prompt
    if file_prompt:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        file_prompt = os.path.join(current_dir, "prompts", f"{file_prompt}.txt")
        if not os.path.exists(file_prompt):
            logger.error(f"File {file_prompt} not found")
            return None
        with open(file_prompt, "r", encoding="utf-8") as f:
            prompt_instructions = f.read()
        base_prompt = prompt_instructions + "\n"
    else:
        base_prompt = ""

    # Process data in batches (or single item if no data)
    data_to_process = (
        [data]
        if data is None
        else [data[i : i + limit] for i in range(0, len(data), limit)]
    )

    for i, batch in enumerate(data_to_process):
        # Prepare full prompt for this batch
        if data is not None:
            json_str = json.dumps(batch, ensure_ascii=False, indent=2)
            prompt_full = base_prompt + prompt + "\n" + json_str + "\n"
        else:
            prompt_full = base_prompt + prompt

        # Make API call
        response = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt_full}],
            model=model,
            max_tokens=15000,
            temperature=temperature,
            response_format={"type": "json_object" if is_json else "text"},
        )
        logger.info("Total tokens: " + str(response.usage.total_tokens))

        content = response.choices[0].message.content
        if is_json:
            try:
                content_json = json.loads(content)
                responses.extend(
                    content_json if isinstance(content_json, list) else [content_json]
                )
            except Exception as e:
                logger.error("Can't parse content to JSON: " + str(e))
                save_errors(content, "ai_resp")
        else:
            responses.append(content)

        if data is not None:
            logger.info(f"Progress: {i*limit+len(batch)}/{len(data)}")

    return responses[0] if data is None else responses
