import telebot
from telebot import types
import pandas as pd
import random
import re
import html
from datetime import datetime, date

import os
bot = telebot.TeleBot(os.getenv("BOT_TOKEN"))

@bot.message_handler(func=lambda message: True, content_types=['text'])
def debug_all_messages(message):
    print("CHAT ID:", message.chat.id)
    print("THREAD ID:", message.message_thread_id)
    print("TEXT:", message.text)

# ----------- экранирование ----------
def escape_html(text):
    if text is None:
        return ""
    return html.escape(str(text))

# ----------- загрузка таблицы ----------
def load_people():
    csv_url = 'https://docs.google.com/spreadsheets/d/1_ExJi6ZqZdzFPeMDTxEZBjAiNI0W6DFCAPGC90nK4Bk/export?format=csv&gid=949169408'
    df = pd.read_csv(csv_url, encoding='utf-8-sig')
    df['published'] = df['published'].astype(str).str.lower()
    df = df[df['published'] == 'true']
    df['id'] = df['id'].astype(str)
    return df


# ----------- КОРОТКАЯ карточка (с фото) ----------
def build_short_card(person, max_len=1024):
    text_blocks = []

    if pd.notna(person.get('artist')) and str(person['artist']).strip():
        text_blocks.append(f"<i>Художник: {escape_html(person['artist'])}</i>")

    if pd.notna(person.get('short_name')) and str(person['short_name']).strip():
        text_blocks.append(f"<b>{escape_html(person['short_name'])}</b>")

    if pd.notna(person.get('status')) and str(person['status']).strip():
        text_blocks.append(escape_html(person['status']))

    if pd.notna(person.get('persecution_articles_criminal_code_ru')) and str(person['persecution_articles_criminal_code_ru']).strip():
        text_blocks.append(f"Статья: {escape_html(person['persecution_articles_criminal_code_ru'])}")

    if pd.notna(person.get('verdict_essence_ru')) and str(person['verdict_essence_ru']).strip():
        text_blocks.append(f"Вердикт: {escape_html(person['verdict_essence_ru'])}")

    if pd.notna(person.get('persecution_case_profile_ru')) and str(person['persecution_case_profile_ru']).strip():
        text_blocks.append(escape_html(person['persecution_case_profile_ru']))

    text = "\n\n".join(text_blocks)

    if len(text) > max_len:
        text = text[:max_len-3] + "..."

    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton('Читать подробнее', callback_data=f"full_{person['id']}"))
    markup.add(types.InlineKeyboardButton('Другой человек', callback_data='random'))
    markup.add(types.InlineKeyboardButton('❤️ Поддержать кампанию', url='https://zaodno.org/r?id=rec4bAhJiKk2l0XZ8'))

    image_url = str(person.get('image', '')).strip()
    return image_url, text, markup


# ----------- ПОЛНАЯ карточка (длинный текст) ----------
def build_full_card(person):
    blocks = []

    def add(title, field):
        if pd.notna(person.get(field)) and str(person[field]).strip():
            blocks.append(f"<b>{escape_html(title)}</b>\n{escape_html(person[field])}")

    if pd.notna(person.get('name')) and str(person['name']).strip():
        blocks.append(f"<b>{escape_html(person['name'])}</b>")
    add("Дата рождения", "birth_year")
    add("Статус", "status")
    add("Где находится", "place")
    add("История", "story")

    text = "\n\n".join(blocks)

    if len(text) > 4096:
        text = text[:4090] + "..."

    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton('⬅️ Назад', callback_data=f"short_{person['id']}"))
    markup.add(types.InlineKeyboardButton('Другой человек', callback_data='random'))

    return text, markup


# ---------- /start ----------
@bot.message_handler(commands=['start'])
def send_welcome(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add('🎨 Смотреть истории',
               '🔎 Найти человека',
               '🎂 Ближайшие дни рождения',
               '❤️ Поддержать кампанию')

    welcome_text = ("Выберите действие ниже:")

    bot.send_message(message.chat.id, welcome_text, reply_markup=markup)


# ---------- случайная история ----------
@bot.message_handler(func=lambda message: message.text == '🎨 Смотреть истории')
def random_story(message):
    df = load_people()
    if df.empty:
        bot.send_message(message.chat.id, 'В базе пока нет опубликованных историй.')
        return

    person = df.sample(1).iloc[0]
    image_url, text, markup = build_short_card(person)

    bot.send_photo(
        message.chat.id,
        image_url,
        caption=text,
        reply_markup=markup,
        parse_mode='HTML'
    )


# ---------- поиск ----------
@bot.message_handler(func=lambda message: message.text == '🔎 Найти человека')
def ask_name(message):
    bot.send_message(message.chat.id, 'Введите имя или фамилию для поиска:')
    bot.register_next_step_handler(message, search_name_step)


def search_name_step(message):
    query = message.text.strip().lower()
    df = load_people()

    results = df[
        df['name'].str.lower().str.contains(query, na=False) |
        df['short_name'].str.lower().str.contains(query, na=False)
    ]

    if results.empty:
        bot.send_message(message.chat.id, 'Совпадений не найдено.')
        return

    markup = types.InlineKeyboardMarkup()
    for _, person in results.iterrows():
        markup.add(types.InlineKeyboardButton(person['short_name'], callback_data=f"short_{person['id']}"))

    bot.send_message(message.chat.id, f'Найдено {len(results)}:', reply_markup=markup)


# ---------- CALLBACK КНОПКИ ----------
@bot.callback_query_handler(func=lambda call: True)
def callback_inline(call):
    try:
        df = load_people()

        if call.data == 'random':
            random_story(call.message)
            bot.answer_callback_query(call.id)
            return

        if call.data.startswith('short_'):
            person_id = call.data.replace('short_', '')
            person = df[df['id'] == person_id].iloc[0]

            image_url, text, markup = build_short_card(person)

            bot.send_photo(
                call.message.chat.id,
                image_url,
                caption=text,
                reply_markup=markup,
                parse_mode='HTML'
            )
            bot.answer_callback_query(call.id)
            return

        if call.data.startswith('full_'):
            person_id = call.data.replace('full_', '')
            person = df[df['id'] == person_id].iloc[0]

            text, markup = build_full_card(person)

            bot.send_message(
                call.message.chat.id,
                text,
                reply_markup=markup,
                parse_mode='HTML'
            )
            bot.answer_callback_query(call.id)
            return

    except Exception as e:
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, f'Ошибка: {e}')


@bot.message_handler(func=lambda message: message.text == '🎂 Ближайшие дни рождения')
def birthdays(message):
    df = load_people()

    if 'birth_year' not in df.columns:
        bot.send_message(message.chat.id, "В таблице нет поля birth_year.")
        return

    today = date.today()
    upcoming = []

    for _, person in df.iterrows():
        raw = str(person.get('birth_year', '')).strip()
        if not raw or raw == 'nan':
            continue

        # формат: 1989-02-23T00:00:00.000Z
        try:
            year, month, day = raw[:10].split('-')
            bday = date(today.year, int(month), int(day))
        except:
            continue

        # если уже прошёл в этом году — переносим на следующий
        if bday < today:
            bday = date(today.year + 1, int(month), int(day))

        days_left = (bday - today).days

        if days_left <= 7:
            upcoming.append((days_left, person, f"{day}.{month}"))

    if not upcoming:
        bot.send_message(message.chat.id, "В ближайшие 7 дней дней рождений нет.")
        return

    # сортировка по ближайшим
    upcoming.sort(key=lambda x: x[0])

    markup = types.InlineKeyboardMarkup()
    text_lines = ["🎂 Ближайшие дни рождения:\n"]

    for days_left, person, human_date in upcoming:
        name = str(person.get('short_name', ''))
        person_id = str(person.get('id'))

        text_lines.append(f"{name} — {human_date} (через {days_left} дн.)")

        # КНОПКА → открывает КРАТКУЮ карточку С ФОТО
        markup.add(
            types.InlineKeyboardButton(
                text=f"{name} ({days_left} дн.)",
                callback_data=f"short_{person_id}"
            )
        )

    bot.send_message(
        message.chat.id,
        "🎂 Ближайшие дни рождения:",
        reply_markup=markup
    )


@bot.message_handler(func=lambda message: message.text == '❤️ Поддержать кампанию')
def donation(message):
    bot.send_message( message.chat.id, 'Кампания #free120 собирает средства для помощи политзаключённым по заявкам доверенных лиц:\n' '— передачи\n— лекарства\n— адвокаты\n— дорога родственникам\n\n' 'Поддержать: https://zaodno.org/r?id=rec4bAhJiKk2l0XZ8' )


if __name__ == '__main__':
    print('Bot is running...')

    bot.polling(none_stop=True)
