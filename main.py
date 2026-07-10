import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message
from groq import AsyncGroq
import os
from dotenv import load_dotenv

# Загружаем переменные из .env файла
load_dotenv()

# --- НАСТРОЙКИ ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_TOKEN = os.getenv("GROQ_TOKEN")

if not TELEGRAM_TOKEN or not GROQ_TOKEN:
    print("❌ Ошибка: Не указан TELEGRAM_TOKEN или GROQ_TOKEN в файле .env")
    sys.exit(1)

# --- КЛИЕНТЫ ---
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

# Создаем клиент Groq
client = AsyncGroq(api_key=GROQ_TOKEN)

# --- ГЛОБАЛЬНЫЙ ПРОМПТ (ДУША БОТА) ---
SYSTEM_PROMPT = """
Ты — эмпатичный и поддерживающий собеседник. Ты не ставишь диагнозы и не назначаешь лечение.

Твои задачи:
1. Внимательно выслушать человека.
2. Признавать и принимать его чувства.
   Примеры: "Понимаю, почему ты злишься...", "Это совершенно нормально — чувствовать грусть в такой ситуации".
3. Задавать уточняющие вопросы, чтобы помочь человеку разобраться в себе.
4. Давать советы только в мягкой, ненавязчивой форме.
   Примеры: "Некоторым людям в такой ситуации помогает...", "Возможно, стоит попробовать подумать о...".

КРИТИЧЕСКИ ВАЖНО:
Если собеседник говорит о суициде, самоповреждении, насилии или нежелании жить, ты ОБЯЗАН:
1. Выразить поддержку и сочувствие.
2. Мягко напомнить, что ты всего лишь программа и не можешь заменить профессионального психолога.
3. Предоставить контакт горячей линии:
   "Пожалуйста, не оставайся один в эту минуту. Позвони на горячую линию: 8-800-2000-122. Это анонимно, бесплатно и круглосуточно. Тебе там помогут."

Отвечай на русском языке. Будь теплым и человечным, но не переигрывай.
"""

# Хранилище историй диалогов
user_contexts = {}


# --- КРИЗИСНЫЙ ДЕТЕКТОР ---
def check_crisis(text: str) -> bool:
    """
    Быстрая проверка на слова-триггеры до отправки в нейросеть.
    Возвращает True, если обнаружены тревожные сигналы.
    """
    danger_words = [
        "суицид", "покончить с собой", "повеситься", "выпиться",
        "резать вены", "не хочу жить", "убить себя", "самоубийство",
        "суицидальные мысли", "навредить себе", "прыгнуть с крыши",
        "хочу умереть", "надоело жить"
    ]
    text_lower = text.lower()
    return any(word in text_lower for word in danger_words)


# --- КОМАНДА /start ---
@dp.message(Command("start"))
async def start_cmd(message: Message):
    user_id = message.from_user.id
    # Очищаем историю при старте
    user_contexts[user_id] = []

    welcome_text = (
        "👋 Привет! Я здесь, чтобы выслушать тебя.\n\n"
        "⚠️ *Важно:* Я — ИИ-бот, а не настоящий психолог. "
        "Я могу поддержать разговор и предложить взглянуть на ситуацию с другой стороны, "
        "но не ставлю диагнозы и не назначаю лечение.\n\n"
        "Пожалуйста, не сообщай мне паспортные данные или точный адрес.\n\n"
        "Расскажи, что у тебя на душе?"
    )
    await message.answer(welcome_text, parse_mode="Markdown")


# --- КОМАНДА /clear ---
@dp.message(Command("clear"))
async def clear_cmd(message: Message):
    user_id = message.from_user.id
    user_contexts[user_id] = []
    await message.answer("🧹 История диалога очищена. Начинаем с чистого листа.")


# --- ОСНОВНОЙ ОБРАБОТЧИК СООБЩЕНИЙ ---
@dp.message()
async def handle_message(message: Message):
    user_id = message.from_user.id
    user_text = message.text

    # Инициализируем историю, если её нет
    if user_id not in user_contexts:
        user_contexts[user_id] = []

    # --- КРИЗИСНЫЙ ДЕТЕКТОР ---
    if check_crisis(user_text):
        crisis_message = (
            "❤️ Мне очень жаль, что ты сейчас проходишь через это. "
            "Твои чувства важны, и ты не один.\n\n"
            "Но я всего лишь программа и не могу заменить профессиональную помощь.\n\n"
            "📞 *Пожалуйста, прямо сейчас позвони на горячую линию:*\n"
            "• 8-800-2000-122 (Россия, круглосуточно, анонимно, бесплатно)\n"
            "• 051 (Москва, неотложная психологическая помощь)\n\n"
            "Там работают люди, которым не все равно. Они выслушают и помогут."
        )
        await message.answer(crisis_message, parse_mode="Markdown")

        # Сохраняем в историю
        user_contexts[user_id].append({"role": "user", "content": user_text})
        user_contexts[user_id].append({"role": "assistant", "content": crisis_message})
        return

    # --- ОБЫЧНЫЙ ДИАЛОГ ---
    # Добавляем сообщение пользователя в историю
    user_contexts[user_id].append({"role": "user", "content": user_text})

    try:
        # Показываем индикатор "печатает"
        await bot.send_chat_action(message.chat.id, action="typing")

        # Отправляем запрос в Groq
        response = await client.chat.completions.create(
            model="llama-3.1-8b-instant",  # Быстрая и бесплатная модель
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                *user_contexts[user_id]  # Передаем всю историю
            ],
            temperature=0.8,  # Небольшая вариативность для естественности
            max_tokens=1000   # Лимит на длину ответа
        )

        bot_answer = response.choices[0].message.content

        # Отправляем ответ
        await message.answer(bot_answer)

        # Сохраняем ответ бота в историю
        user_contexts[user_id].append({"role": "assistant", "content": bot_answer})

        # Ограничиваем историю (последние 20 сообщений = 10 пар)
        if len(user_contexts[user_id]) > 20:
            user_contexts[user_id] = user_contexts[user_id][-20:]

    except Exception as e:
        logging.error(f"Ошибка при обращении к Groq API: {e}")
        await message.answer(
            "😔 Прости, произошла техническая ошибка. "
            "Попробуй отправить сообщение еще раз."
        )


# --- ТОЧКА ВХОДА ---
async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )
    logger = logging.getLogger(__name__)

    print("=" * 50)
    print("🤖 Бот-психолог запускается...")
    print(f"🧠 Провайдер: Groq")
    print(f"🧠 Модель: llama-3.1-8b-instant")
    print(f"💰 Тариф: Бесплатный (до 30 запросов/мин)")
    print(f"💾 Хранилище: в памяти (замените на БД для продакшена)")
    print("📋 Команды:")
    print("   /start — начать диалог")
    print("   /clear — очистить историю")
    print("=" * 50)

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        print("\n👋 Бот остановлен.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Бот остановлен пользователем.")