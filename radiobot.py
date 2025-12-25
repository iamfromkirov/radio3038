# bot.py
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

BOT_TOKEN = "000"
WEB_APP_URL = "https://iamfromkirov.github.io/radio3038/radio.html"  # ← ваша Web App

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    web_app = types.WebAppInfo(url=WEB_APP_URL)
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="▶️ Слушать радио", web_app=web_app)]
    ])
    await message.answer("Нажмите кнопку, чтобы включить радио:", reply_markup=keyboard)

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
