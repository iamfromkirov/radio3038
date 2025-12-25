# bot.py
import asyncio
import re
import requests
import tempfile
import os
import csv
from datetime import datetime
from zoneinfo import ZoneInfo
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from bs4 import BeautifulSoup
import urllib.parse

BOT_TOKEN = "8247834027:AAFainpelNW8GBT0W9OKRGOYtuquyVcTkNI"
WEB_APP_URL = "https://iamfromkirov.github.io/radio3038/radio.html"
LOG_FILE = "users.csv"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

MOSCOW_TZ = ZoneInfo("Europe/Moscow")

def clean_query(text: str) -> str:
    return re.sub(r'[^a-zA-Zа-яА-Я0-9\s]', ' ', text).strip()

def parse_duration(time_str: str) -> int:
    parts = list(map(int, time_str.split(':')))
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    elif len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    return 0

def search_tracks(query: str):
    url = f"https://rus.hitmotop.com/search?q={urllib.parse.quote(query)}"
    headers = {'User-Agent': 'Mozilla/5.0'}
    r = requests.get(url, headers=headers)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, 'html.parser')
    tracks = []
    for li in soup.select('ul.tracks__list li.tracks__item'):
        meta = li.get('data-musmeta')
        if not meta:
            continue
        try:
            import json
            meta = json.loads(meta.replace('&quot;', '"'))
        except:
            continue

        title = meta.get('title', '')
        artist = meta.get('artist', '')
        download_tag = li.select_one('a.track__download-btn[href]')
        if not download_tag:
            continue
        download_url = download_tag['href'].strip()

        time_elem = li.select_one('.track__fulltime')
        duration_sec = 0
        if time_elem:
            duration_sec = parse_duration(time_elem.get_text(strip=True))

        tracks.append({
            'title': title,
            'artist': artist,
            'url': download_url,
            'duration_sec': duration_sec
        })
    return tracks

async def download_audio(url: str) -> str:
    headers = {'User-Agent': 'Mozilla/5.0'}
    resp = requests.get(url, headers=headers, stream=True)
    resp.raise_for_status()
    with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)
        return f.name

def get_main_reply_keyboard():
    builder = ReplyKeyboardBuilder()
    web_app = types.WebAppInfo(url=WEB_APP_URL)
    builder.button(text="📻 Радио", web_app=web_app)
    builder.adjust(1)
    return builder.as_markup(resize_keyboard=True, input_field_placeholder="Отправьте название песни...")

def log_request(user: types.User, query_text: str):
    """Записывает запрос в users.csv с разделителем ';'."""
    moscow_time = datetime.now(MOSCOW_TZ).strftime("%d.%m.%Y %H:%M:%S")
    file_exists = os.path.isfile(LOG_FILE)

    with open(LOG_FILE, "a", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, delimiter=';')
        if not file_exists:
            writer.writerow(["username", "user_id", "language_code", "запрос", "время_МСК"])
        writer.writerow([
            user.username or "",
            user.id,
            user.language_code or "",
            query_text,
            moscow_time
        ])

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "🎧 Отправьте название песни — я найду и пришлю её!\n\n"
        "Или нажмите «📻 Радио» ниже, чтобы слушать онлайн.",
        reply_markup=get_main_reply_keyboard()
    )

@dp.message(Command("3038"))
async def send_report(message: types.Message):
    if not os.path.isfile(LOG_FILE):
        await message.reply("Нет данных для отчёта.")
        return

    # Проверим, есть ли что-то кроме заголовка
    with open(LOG_FILE, "r", encoding="utf-8-sig") as f:
        lines = f.readlines()
        if len(lines) <= 1:
            await message.reply("Нет данных для отчёта.")
            os.remove(LOG_FILE)  # на всякий случай
            return

    try:
        await bot.send_document(
            chat_id=message.chat.id,
            document=types.FSInputFile(LOG_FILE),
            caption="📊 Отчёт по запросам"
        )
        # Очищаем файл: перезаписываем только заголовок
        with open(LOG_FILE, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f, delimiter=';')
            writer.writerow(["username", "user_id", "language_code", "запрос", "время_МСК"])
    except Exception as e:
        await message.reply(f"Ошибка отправки: {str(e)}")

@dp.message(F.text & (F.text != "📻 Радио"))
async def handle_music_search(message: types.Message, state: FSMContext):
    log_request(message.from_user, message.text)

    query = clean_query(message.text)
    all_tracks = search_tracks(query)
    tracks = [t for t in all_tracks if t['duration_sec'] <= 600]

    if not all_tracks:
        await message.reply("❌ Ничего не найдено.")
        return
    if not tracks:
        await message.reply("❌ Найдено файлов: 0 (все длиннее 10 минут).")
        return

    await state.set_data({"tracks": tracks, "page": 0})
    await message.reply(f"✅ Найдено файлов: {len(tracks)}")

    first = tracks[0]
    try:
        path = await download_audio(first['url'])
        caption = f"{first['artist']} – {first['title']}"
        await bot.send_audio(
            chat_id=message.chat.id,
            audio=types.FSInputFile(path, filename=f"{caption}.mp3"),
            caption=caption
        )
        os.unlink(path)
    except Exception as e:
        await message.reply(f"⚠️ Ошибка загрузки: {str(e)}")
        return

    await show_track_buttons(message.chat.id, tracks, page=0, state=state)

async def show_track_buttons(chat_id, tracks, page, state: FSMContext):
    start = 1 + page * 8
    end = start + 8
    chunk = tracks[start:end]

    if not chunk:
        return

    builder = InlineKeyboardBuilder()
    for i, track in enumerate(chunk, start=start):
        builder.button(
            text=f"{track['artist']} – {track['title']}",
            callback_data=f"track:{i}"
        )

    if end < len(tracks):
        builder.button(text="➡️ ЕЩЁ", callback_data=f"more:{page + 1}")

    builder.adjust(1)
    await bot.send_message(chat_id, "Другие варианты:", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("track:"))
async def send_selected_track(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    tracks = data.get("tracks", [])
    try:
        idx = int(callback.data.split(":")[1])
        track = tracks[idx]
        path = await download_audio(track['url'])
        caption = f"{track['artist']} – {track['title']}"
        await bot.send_audio(
            chat_id=callback.message.chat.id,
            audio=types.FSInputFile(path, filename=f"{caption}.mp3"),
            caption=caption
        )
        os.unlink(path)
    except Exception as e:
        await callback.message.reply(f"⚠️ Ошибка: {str(e)}")
    await callback.answer()

@dp.callback_query(F.data.startswith("more:"))
async def show_more(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    tracks = data.get("tracks", [])
    page = int(callback.data.split(":")[1])
    await show_track_buttons(callback.message.chat.id, tracks, page, state)
    await callback.answer()

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())