from openai import OpenAI
from yt_fetcher.app.config import settings


client = OpenAI(
    # This is the default and can be omitted
    api_key=settings.OAI_API_KEY,
)


# Функция для отправки запроса к ChatGPT
def chat_with_gpt(prompt):
    response = client.chat.completions.create(
        messages=[
            {
                "role": "user",
                "content": "Say this is a test",
            }
        ],
        model="gpt-3.5-turbo",
        max_tokens=1000,  # Максимальное количество токенов в ответе
        temperature=0.7,  # Креативность (от 0 до 1)
    )

    return response["choices"][0]["message"]["content"]


# Пример использования функции
prompt = "Расскажи, как написать запрос к ChatGPT на Python."
response = chat_with_gpt(prompt)
print(response)
