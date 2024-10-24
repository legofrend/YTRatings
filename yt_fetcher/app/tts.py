from gtts import gTTS
import os


def text_to_speech(text, lang="ru"):
    # Преобразование текста в речь
    tts = gTTS(text=text, lang=lang)

    # Сохранение аудио в файл
    audio_file = "output.mp3"
    tts.save(audio_file)

    # Воспроизведение аудио (для локальной среды)
    os.system(f"start {audio_file}")  # Для Windows
    # os.system(f"afplay {audio_file}")  # Для Mac
    # os.system(f"mpg321 {audio_file}")  # Для Linux

    return audio_file


# Пример использования
text = "Привет! Это пример преобразования текста в речь."
audio_file = text_to_speech(text)
print(f"Аудио сохранено в {audio_file}")
