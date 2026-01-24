import asyncio
import logging
import requests
import os
import re
import io
import matplotlib
# Serverda (ekransiz) ishlashi uchun Agg rejimini yoqish shart
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from aiogram.types import BufferedInputFile
from aiohttp import web

# Telegram bot tokeningiz
TOKEN = "8392318346:AAFjf3MqlLlXDgGAuqL9HkVHyUvQpk0XlBg"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher()

cached_rates = {}
USER_FILE = "users.txt"
LANG_FILE = "users_lang.txt"

# --- Tillarda lug'at ---
TEXTS = {
    'uz': {
        'start': "👋 <b>Valyuta botiga xush kelibsiz!</b>\n\n💰 Kalkulyatordan foydalanish uchun:\n1. Shunchaki son yuboring (masalan: 200) - uni so'mga o'giraman.\n2. Son va 'som' deb yozing (masalan: 200 som) - uni valyutalarga bo'lib beraman.",
        'btn_rates': "💰 Kurslarni ko'rish",
        'btn_stats': "📊 O'zgarishlar va Grafik",
        'btn_calc_help': "🧮 Yordam",
        'select_graph': "Qaysi valyuta bo'yicha grafikni ko'rmoqchisiz?",
        'calc_help': "🔢 <b>Kalkulyator qoidalari:</b>\n\n- <code>500</code> -> Chet el valyutasidan so'mga\n- <code>500 som</code> -> So'mdan chet el valyutasiga",
        'wait_chart': "⏳ Grafik tayyorlanmoqda...",
        'trend_up': "Ko'tarildi", 'trend_down': "Tushdi", 'trend_no': "O'zgarmadi"
    },
    'ru': {
        'start': "👋 <b>Добро пожаловать!</b>\n\n1. Отправьте число (напр: 200) - переведу в сумы.\n2. Отправьте число + 'som' (напр: 200 som) - переведу в валюту.",
        'btn_rates': "💰 Курсы валют",
        'btn_stats': "📊 Графики",
        'btn_calc_help': "🧮 Помощь",
        'select_graph': "По какой валюте показать график?",
        'calc_help': "🔢 <b>Как пользоваться:</b>\n\n- <code>500</code> -> Из валюты в сумы\n- <code>500 som</code> -> Из сумов в валюту",
        'wait_chart': "⏳ График готовится...",
        'trend_up': "Поднялся", 'trend_down': "Упал", 'trend_no': "Не изменился"
    },
    'en': {
        'start': "👋 <b>Welcome!</b>\n\n1. Send a number (e.g., 200) - I'll convert to UZS.\n2. Send number + 'som' (e.g., 200 som) - I'll convert to currencies.",
        'btn_rates': "💰 View Rates",
        'btn_stats': "📊 Charts",
        'btn_calc_help': "🧮 Help",
        'select_graph': "Which currency chart to show?",
        'calc_help': "🔢 <b>Calculator rules:</b>\n\n- <code>500</code> -> Currency to UZS\n- <code>500 som</code> -> UZS to Currency",
        'wait_chart': "⏳ Preparing chart...",
        'trend_up': "Rose", 'trend_down': "Dropped", 'trend_no': "No change"
    }
}

# --- Foydalanuvchi ma'lumotlari funksiyalari ---
def get_user_lang(user_id):
    if not os.path.exists(LANG_FILE): return 'uz'
    try:
        with open(LANG_FILE, "r") as f:
            for line in f:
                if ':' in line:
                    uid, lang = line.strip().split(':')
                    if uid == str(user_id): return lang
    except: pass
    return 'uz'

def set_user_lang(user_id, lang):
    users = {}
    if os.path.exists(LANG_FILE):
        try:
            with open(LANG_FILE, "r") as f:
                for line in f:
                    if ':' in line:
                        uid, l = line.strip().split(':')
                        users[uid] = l
        except: pass
    users[str(user_id)] = lang
    with open(LANG_FILE, "w") as f:
        for uid, l in users.items(): f.write(f"{uid}:{l}\n")

def add_user(user_id):
    if not os.path.exists(USER_FILE):
        with open(USER_FILE, "w") as f: f.write(f"{user_id}\n")
        return True
    with open(USER_FILE, "r") as f:
        users = f.read().splitlines()
    if str(user_id) not in users:
        with open(USER_FILE, "a") as f: f.write(f"{user_id}\n")
        return True
    return False

# --- Tugmalar ---
def lang_menu():
    builder = InlineKeyboardBuilder()
    builder.button(text="🇺🇿 O'zbekcha", callback_data="lang_uz")
    builder.button(text="🇷🇺 Русский", callback_data="lang_ru")
    builder.button(text="🇺🇸 English", callback_data="lang_en")
    builder.adjust(1)
    return builder.as_markup()

def main_menu(lang):
    builder = ReplyKeyboardBuilder()
    builder.button(text=TEXTS[lang]['btn_rates'])
    builder.button(text=TEXTS[lang]['btn_stats'])
    builder.button(text=TEXTS[lang]['btn_calc_help'])
    builder.adjust(2, 1)
    return builder.as_markup(resize_keyboard=True)

def graph_menu():
    builder = InlineKeyboardBuilder()
    for code in ['USD', 'EUR', 'RUB', 'KRW', 'INR', 'CNY']:
        builder.button(text=code, callback_data=f"graph_{code}")
    builder.adjust(3)
    return builder.as_markup()

# --- Grafik chizish (O'tgan kunlar ko'rinadigan qilib sozlandi) ---
async def send_weekly_chart(message: types.Message, currency_code: str, lang: str):
    # API dan 12 kunlik zaxira bilan ma'lumot so'raymiz (shanba-yakshanbalar uchun)
    end_date = datetime.now().strftime("%d.%m.%Y")
    start_date = (datetime.now() - timedelta(days=12)).strftime("%d.%m.%Y")
    url = f"https://cbu.uz/uz/arkhiv-kursov-valyut/json/{currency_code}/{start_date}/{end_date}/"
    try:
        r = requests.get(url, timeout=20)
        if r.status_code == 200:
            data = r.json()
            # Eng oxirgi 7 ta o'zgarishni olamiz va teskari (eskidan yangiga) qilamiz
            if len(data) > 7: data = data[:7]
            data.reverse()
            
            dates = [item['Date'][:5] for item in data]
            rates = [float(item['Rate']) for item in data]
            
            plt.figure(figsize=(9, 5))
            plt.plot(dates, rates, marker='o', color='forestgreen', linewidth=2.5, markersize=7)
            
            # Nuqtalar ustiga qiymatlarni yozish
            for i, rate in enumerate(rates):
                plt.text(i, rate, f"{rate:,.0f}", ha='center', va='bottom', fontsize=9, fontweight='bold')
            
            plt.title(f"{currency_code} - Last 7 Days Trend")
            plt.grid(True, linestyle='--', alpha=0.5)
            
            buf = io.BytesIO()
            plt.savefig(buf, format='png', bbox_inches='tight')
            buf.seek(0)
            plt.close()
            
            photo = BufferedInputFile(buf.read(), filename="chart.png")
            await message.answer_photo(photo, caption=f"📊 <b>{currency_code}</b> trend")
    except Exception as e:
        logging.error(f"Grafik xatosi: {e}")
        await message.answer("⚠️ System error while generating chart.")

# --- Handlerlar ---
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    add_user(message.from_user.id)
    await message.answer("Tilni tanlang / Выберите язык / Choose language:", reply_markup=lang_menu())

@dp.callback_query(F.data.startswith("lang_"))
async def set_lang(callback: types.CallbackQuery):
    lang = callback.data.split('_')[1]
    set_user_lang(callback.from_user.id, lang)
    await callback.message.answer(TEXTS[lang]['start'], parse_mode="HTML", reply_markup=main_menu(lang))
    await callback.answer()

@dp.message(F.text.in_([TEXTS['uz']['btn_rates'], TEXTS['ru']['btn_rates'], TEXTS['en']['btn_rates']]))
async def kurs_cmd(message: types.Message):
    if not cached_rates:
        await message.answer("⚠️ No data.")
        return
    date = list(cached_rates.values())[0]['date']
    text = f"📅 <b>{date}:</b>\n\n"
    for code, info in cached_rates.items():
        diff = info['diff']
        trend = "🟢 🔺" if diff > 0 else "🔴 🔻" if diff < 0 else "⚪️ ➖"
        text += f"{trend} <b>{info['name']}</b>: {info['rate']:,} ({diff})\n"
    await message.answer(text, parse_mode="HTML")

@dp.message(F.text.in_([TEXTS['uz']['btn_stats'], TEXTS['ru']['btn_stats'], TEXTS['en']['btn_stats']]))
async def stats_info(message: types.Message):
    lang = get_user_lang(message.from_user.id)
    text = f"📈 <b>{TEXTS[lang]['btn_stats']}:</b>\n\n"
    for code, info in cached_rates.items():
        diff = info['diff']
        tr = TEXTS[lang]['trend_up'] if diff > 0 else TEXTS[lang]['trend_down'] if diff < 0 else TEXTS[lang]['trend_no']
        text += f"🔹 <b>{code}</b>: {diff} ({tr})\n"
    await message.answer(text, parse_mode="HTML")
    await message.answer(TEXTS[lang]['select_graph'], reply_markup=graph_menu())

@dp.callback_query(F.data.startswith("graph_"))
async def handle_graph_choice(callback: types.CallbackQuery):
    lang = get_user_lang(callback.from_user.id)
    code = callback.data.split('_')[1]
    await callback.message.answer(TEXTS[lang]['wait_chart'])
    await send_weekly_chart(callback.message, code, lang)
    await callback.answer()

@dp.message(F.text.in_([TEXTS['uz']['btn_calc_help'], TEXTS['ru']['btn_calc_help'], TEXTS['en']['btn_calc_help']]))
async def help_calc(message: types.Message):
    lang = get_user_lang(message.from_user.id)
    await message.answer(TEXTS[lang]['calc_help'], parse_mode="HTML")

# --- AQLLI KALKULYATOR ---
@dp.message(F.text)
async def calculator(message: types.Message):
    text_lower = message.text.lower()
    is_uzs = any(x in text_lower for x in ["som", "so'm", "somm", "sum"])
    match = re.search(r"(\d+[\d.,]*)", message.text)
    if match and cached_rates:
        try:
            amount = float(match.group(1).replace(',', '.'))
            if is_uzs:
                res = f"🔄 <b>{amount:,.0f} so'm miqdori:</b>\n\n"
                for code, info in cached_rates.items():
                    val = amount / info['rate']
                    res += f"💰 {amount:,.0f} so'm = <b>{val:,.2f} {code}</b>\n"
            else:
                res = f"🔄 <b>{amount:,.2f} (Valyuta) so'mga o'girilganda:</b>\n\n"
                for code, info in cached_rates.items():
                    uzs = amount * info['rate']
                    res += f"💰 {amount:,.2f} <b>{code}</b> = <b>{uzs:,.2f} so'm</b>\n"
            await message.answer(res, parse_mode="HTML")
        except: pass

# --- Universal funksiyalar ---
def fetch_rates():
    url = "https://cbu.uz/uz/arkhiv-kursov-valyut/json/"
    try:
        r = requests.get(url, timeout=20)
        if r.status_code == 200:
            data = r.json()
            targets = {'USD', 'EUR', 'RUB', 'KRW', 'INR', 'CNY'}
            rates_dict = {}
            for item in data:
                code = item['Ccy']
                if code in targets:
                    rates_dict[code] = {
                        'name': item['CcyNm_UZ'],
                        'rate': float(item['Rate']),
                        'diff': float(item['Diff']),
                        'date': item['Date']
                    }
            return rates_dict
    except: return None

async def handle(request): return web.Response(text="Bot Live!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', int(os.environ.get("PORT", 8080)))
    await site.start()

async def update_rates_loop():
    global cached_rates
    while True:
        data = fetch_rates()
        if data: cached_rates = data
        await asyncio.sleep(7200)

async def main():
    global cached_rates
    cached_rates = fetch_rates() or {}
    await start_web_server()
    asyncio.create_task(update_rates_loop())
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
