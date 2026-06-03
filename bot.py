import asyncio
import json
import os
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from anthropic import Anthropic

BOT_TOKEN = os.environ["BOT_TOKEN"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
claude = Anthropic(api_key=ANTHROPIC_API_KEY)

SYSTEM_PROMPT = """Ты помощник агронома. Твоя задача — извлечь данные из отчёта о полевых работах и вернуть их в формате JSON.

Из сообщения извлеки:
- operation_type: тип работы (уборка, обработка, десикация, посев и т.д.)
- crop: культура (пшеница, горох, кукуруза и т.д.)
- fields: список полей, каждое содержит:
  - name: название поля
  - area_ha: убранная/обработанная площадь в га (число)
  - gross_kg: вал в кг (если указан в тоннах — перевести в кг, число)
- total_area_ha: итого площадь (число)
- total_gross_kg: итого вал в кг (число)
- yield_centner_per_ha: урожайность в ц/га (если не указана — посчитай сам из total_gross_kg и total_area_ha, округли до 1 знака)
- machines_count: количество техники (число)
- machines_type: тип техники (комбайн, опрыскиватель и т.д.)
- plan_ha: план в га (если есть, число)
- fact_ha: факт в га (если есть, число)
- remainder_ha: остаток в га (если есть, число)
- date: дата (если указана)
- notes: любые дополнительные заметки

Если каких-то данных нет — ставь null.
Верни ТОЛЬКО JSON без пояснений, без markdown, без ```."""


def format_report(data: dict) -> str:
    lines = []

    op = (data.get("operation_type") or "Работы").capitalize()
    crop = data.get("crop") or ""

    emoji_map = {
        "уборка": "🌾", "обработка": "✅", "десикация": "✅",
        "посев": "🌱", "опрыскивание": "✅"
    }
    e = emoji_map.get(op.lower(), "📋")

    lines.append(f"{e} {op} {crop}:")
    lines.append("")

    for field in data.get("fields") or []:
        name = field.get("name")
        area = field.get("area_ha")
        gross = field.get("gross_kg")
        if name:
            lines.append(f"Поле {name}:")
        if area is not None:
            lines.append(f"Убранная площадь – {area} га.")
        if gross is not None:
            lines.append(f"Вал – {int(gross):,} кг.".replace(",", " "))
        lines.append("")

    # Plan/fact block
    if data.get("plan_ha") is not None:
        lines.append(f"План: {data['plan_ha']} га")
    if data.get("fact_ha") is not None:
        lines.append(f"Факт: {data['fact_ha']} га.")
    if data.get("machines_count") is not None:
        mtype = data.get("machines_type") or "ед."
        lines.append(f"Кол-во техники: {data['machines_count']} {mtype}.")
    if data.get("plan_ha") and data.get("fact_ha"):
        diff = data["fact_ha"] - data["plan_ha"]
        sign = "+" if diff >= 0 else ""
        lines.append(f"План/факт за день: {sign}{diff}/{data['fact_ha']} га.")
    if data.get("remainder_ha") is not None:
        lines.append(f"Остаток: {data['remainder_ha']} га.")

    if data.get("plan_ha") is not None:
        lines.append("")

    # Totals
    if data.get("total_area_ha") is not None:
        lines.append(f"Итого убранная площадь – {data['total_area_ha']} га.")
    if data.get("total_gross_kg") is not None:
        lines.append(f"Итого вал за день: {int(data['total_gross_kg']):,} кг.".replace(",", " "))
    if data.get("yield_centner_per_ha") is not None:
        lines.append(f"Урожайность – {data['yield_centner_per_ha']} ц/га.")
    if data.get("machines_count") is not None and not data.get("plan_ha"):
        mtype = data.get("machines_type") or "комбайна"
        lines.append(f"Кол-во техники: {data['machines_count']} {mtype}.")

    if data.get("notes"):
        lines.append("")
        lines.append(f"📝 {data['notes']}")

    return "\n".join(lines).strip()


@dp.message(CommandStart())
async def start(message: types.Message):
    await message.answer(
        "👋 Привет! Я агро-бот.\n\n"
        "Отправь мне отчёт о полевых работах в любом формате — "
        "я структурирую его и красиво оформлю.\n\n"
        "Например:\n"
        "_убрали горох на поле А43, 70 га, намолот 153 тонны, 2 комбайна_",
        parse_mode="Markdown"
    )


@dp.message()
async def handle_message(message: types.Message):
    user_text = message.text or message.caption
    if not user_text:
        await message.answer("Пришли текстовый отчёт, и я его оформлю 👍")
        return

    await bot.send_chat_action(message.chat.id, "typing")

    try:
        response = claude.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=1000,
            messages=[{
                "role": "user",
                "content": SYSTEM_PROMPT + "\n\nСообщение пользователя:\n" + user_text
            }]
        )

       raw = response.content[0].text.strip()
# Убираем markdown-блоки если есть
raw = raw.replace("```json", "").replace("```", "").strip()
data = json.loads(raw)
        report = format_report(data)
        await message.answer(report)

    except json.JSONDecodeError:
        await message.answer("⚠️ Не смог разобрать отчёт. Попробуй переформулировать.")
    except Exception as e:
        await message.answer(f"⚠️ Ошибка: {str(e)}")


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
