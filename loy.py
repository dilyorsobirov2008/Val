import asyncio
import logging
import requests
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

# Telegram bot tokeningiz
TOKEN = "8394467661:AAEA6HvgBFIA-cL_CAYrWn2EcsSePwtW5zY"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher()

def get_rates():
    """Markaziy Bank API dan kurslarni olish (NBUga qaraganda barqaror)"""
    url = "https://cbu.uz/uz/arkhiv-kursov-valyut/json/"
    try:
        # Browser kabi so'rov yuborish (bloklanmaslik uchun)
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get(url, headers=headers, timeout=20)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        logging.error(f"Ulanishda xato: {e}")
    return None

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer("Salom! Valyuta kurslarini ko'rish uchun /kurs buyrug'ini yuboring.")

@dp.message(Command("kurs"))
async def kurs_cmd(message: types.Message):
    data = get_rates()
    if not data:
        await message.answer("❌ Bank serveri bilan bog'lanishda xatolik. Birozdan so'ng urinib ko'ring.")
        return

    # Bizga kerakli valyutalar
    targets = {
        'USD': 'AQSH Dollari', 
        'EUR': 'Yevro', 
        'RUB': 'Rossiya Rubli', 
        'KRW': 'Koreya Voni'
    }
    
    text = "💰 <b>Bugungi valyuta kurslari:</b>\n\n"
    
    found = False
    for item in data:
        code = item['Ccy'] # Markaziy bankda kod 'Ccy' deb nomlanadi
        if code in targets:
            price = item['Rate']
            text += f"🔹 <b>{targets[code]}</b>\n1 {code} = {price} so'm\n\n"
            found = True
    
    if not found:
        text = "⚠️ Valyuta ma'lumotlari topilmadi."
    
    await message.answer(text, parse_mode="HTML")

async def main():
    print("Bot muvaffaqiyatli ishga tushdi...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())