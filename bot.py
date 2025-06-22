import os
import logging
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Optional

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message
from dotenv import load_dotenv
import openai
import asyncio

# ========== НАСТРОЙКА ЛОГИРОВАНИЯ ==========
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ========== ЗАГРУЗКА ПЕРЕМЕННЫХ ОКРУЖЕНИЯ ==========
load_dotenv()

# ========== КОНФИГУРАЦИЯ ==========
class Config:
    def __init__(self):
        self.TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
        self.OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
        self.OPENROUTER_API_BASE = "https://openrouter.ai/api/v1"
        self.REQUEST_TIMEOUT = 30  # Таймаут запроса в секундах
        self.RATE_LIMIT = 3  # Максимум запросов в минуту
        self.MODEL = "mistralai/mistral-small-3.2-24b-instruct:free"

config = Config()

# ========== НАСТРОЙКА OPENROUTER ==========
openai.api_key = config.OPENROUTER_API_KEY
openai.api_base = config.OPENROUTER_API_BASE

# ========== СИСТЕМА ОГРАНИЧЕНИЯ ЗАПРОСОВ ==========
class RateLimiter:
    def __init__(self):
        self.user_requests = defaultdict(list)
    
    def is_rate_limited(self, user_id: int) -> bool:
        """Проверяет, превысил ли пользователь лимит запросов"""
        now = datetime.now()
        self.user_requests[user_id] = [
            req for req in self.user_requests[user_id]
            if req > now - timedelta(minutes=1)
        ]
        if len(self.user_requests[user_id]) >= config.RATE_LIMIT:
            return True
        self.user_requests[user_id].append(now)
        return False

rate_limiter = RateLimiter()

# ========== ОСНОВНЫЕ ФУНКЦИИ ==========
async def get_llm_response(user_id: int, message_text: str) -> Optional[str]:
    """
    Получает ответ от языковой модели
    Возвращает строку с ответом или None в случае ошибки
    """
    try:
        if rate_limiter.is_rate_limited(user_id):
            return "⚠️ Слишком много запросов. Пожалуйста, подождите минуту."
            
        response = await asyncio.wait_for(
            openai.ChatCompletion.acreate(
                model=config.MODEL,
                messages=[{"role": "user", "content": message_text}],
                timeout=config.REQUEST_TIMEOUT
            ),
            timeout=config.REQUEST_TIMEOUT
        )
        return response.choices[0].message['content']
    except asyncio.TimeoutError:
        logger.warning(f"Таймаут запроса для пользователя {user_id}")
        return "⌛ Время ожидания ответа истекло. Попробуйте позже."
    except Exception as e:
        logger.error(f"Ошибка для пользователя {user_id}: {str(e)}", exc_info=True)
        return None

# ========== ИНИЦИАЛИЗАЦИЯ БОТА ==========
bot = Bot(token=config.TELEGRAM_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# ========== ОБРАБОТЧИКИ КОМАНД ==========
@dp.message(Command("start", "reset"))
async def handle_start_reset(message: Message) -> None:
    """Обрабатывает команды /start и /reset"""
    welcome_text = (
        "👋 Привет! Я ваш умный помощник.\n"
        "📝 История диалога сброшена.\n"
        "💡 Как я могу помочь вам сегодня?"
    )
    await message.answer(welcome_text)

@dp.message(Command("help"))
async def handle_help(message: Message) -> None:
    """Обрабатывает команду /help"""
    help_text = (
        "ℹ️ <b>Справка по боту</b>\n\n"
        "📌 Просто отправьте мне сообщение, и я постараюсь ответить!\n"
        "⏳ Если я не отвечаю, сервер может быть перегружен - попробуйте позже\n"
        "🚫 Ограничение: не более 3 запросов в минуту\n\n"
        "🔄 <code>/reset</code> - сбросить историю диалога\n"
        "❓ <code>/help</code> - показать эту справку"
    )
    await message.answer(help_text, parse_mode="HTML")

# ========== ОБРАБОТЧИК СООБЩЕНИЙ ==========
@dp.message()
async def process_message(message: Message) -> None:
    """Обрабатывает все входящие сообщения"""
    try:
        user_id = message.from_user.id
        logger.info(f"Новый запрос от {user_id}: {message.text[:50]}...")
        
        # Отправляем уведомление о начале обработки
        processing_msg = await message.answer("🔄 Обрабатываю ваш запрос...")
        
        # Получаем ответ от модели
        response = await get_llm_response(user_id, message.text)
        
        # Удаляем сообщение о обработке
        try:
            await bot.delete_message(
                chat_id=processing_msg.chat.id,
                message_id=processing_msg.message_id
            )
        except Exception as e:
            logger.warning(f"Не удалось удалить сообщение: {str(e)}")
        
        # Отправляем ответ или сообщение об ошибке
        if response is not None:
            await message.answer(response)
        else:
            await message.answer(
                "⚠️ Произошла ошибка при обработке запроса.\n"
                "Попробуйте переформулировать вопрос или повторите позже."
            )
            
    except Exception as e:
        logger.critical(f"Критическая ошибка: {str(e)}", exc_info=True)
        await message.answer(
            "⛔ Произошла непредвиденная ошибка.\n"
            "Разработчик уже уведомлен. Пожалуйста, попробуйте позже."
        )

# ========== ЗАПУСК БОТА ==========
if __name__ == "__main__":
    logger.info("Запуск бота...")
    try:
        asyncio.run(dp.start_polling(bot))
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")
    except Exception as e:
        logger.critical(f"Крах бота: {str(e)}", exc_info=True)
    finally:
        logger.info("Бот завершил работу")
