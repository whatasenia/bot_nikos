from handlers import bot
from database import init_db

if __name__ == "__main__":
    init_db()
    print("База данных инициализирована. Бот запущен.")

    bot.infinity_polling(timeout=10, long_polling_timeout=5)
