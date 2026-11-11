import asyncio
import sqlite3
from datetime import datetime

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder

# =====================================================================
# 1. НАСТРОЙКИ И ТВОИ КАНАЛЫ (УЖЕ ВШИТЫ В КОД)
# =====================================================================
BOT_TOKEN = "9018481498:AAEuBzdeNT5m3kx0bkwhaul1Yth-whAXVnU"
ADMIN_ID = 8631078624

# 3 приватных канала, в которые нужно подать заявку:
PRESET_SPONSORS = [
    "-1003957794937",
    "-1004466690167",
    "-1004482500774",
]

# Главный приватный канал, ссылка на который выдается после проверки:
TARGET_CHANNEL_ID = "-1003246253184"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# =====================================================================
# 2. БАЗА ДАННЫХ (SQLite)
# =====================================================================
def init_db():
    conn = sqlite3.connect("funnel_bot.db")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            status TEXT DEFAULT 'new',
            joined_date TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS sponsors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id TEXT UNIQUE,
            title TEXT,
            invite_link TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS user_requests (
            user_id INTEGER,
            chat_id TEXT,
            PRIMARY KEY (user_id, chat_id)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    conn.commit()
    conn.close()

async def auto_setup_channels():
    """
    При запуске бот сам проверяет 3 канала-спонсора и 1 главный канал,
    берет их названия и автоматически создает ссылки с заявкой на вступление!
    """
    conn = sqlite3.connect("funnel_bot.db")
    c = conn.cursor()

    print("🔄 Проверяю доступ к твоим 4 каналам и генерирую ссылки с заявками...")

    # 1. Настраиваем 3 канала-спонсора
    for idx, ch_id in enumerate(PRESET_SPONSORS, start=1):
        c.execute("SELECT title, invite_link FROM sponsors WHERE chat_id = ?", (ch_id,))
        row = c.fetchone()
        # Если канала еще нет в базе или ссылка не создана — создаем автоматически
        if not row or not row[1] or row[1].startswith("https://t.me/+ОБНОВИТЕ"):
            try:
                chat = await bot.get_chat(int(ch_id))
                link_obj = await bot.create_chat_invite_link(
                    chat_id=int(ch_id),
                    name="Бот ОП (Заявки)",
                    creates_join_request=True
                )
                title = chat.title or f"Канал №{idx}"
                c.execute(
                    "INSERT OR REPLACE INTO sponsors (chat_id, title, invite_link) VALUES (?, ?, ?)",
                    (ch_id, title, link_obj.invite_link)
                )
                print(f"✅ Спонсор {idx} подключен: «{title}» ({ch_id}) -> {link_obj.invite_link}")
            except Exception as e:
                print(f"⚠️ ВНИМАНИЕ: Бот еще не админ в канале {ch_id} (или нет права создавать ссылки): {e}")
                if not row:
                    c.execute(
                        "INSERT OR IGNORE INTO sponsors (chat_id, title, invite_link) VALUES (?, ?, ?)",
                        (ch_id, f"Приватный канал №{idx}", "https://t.me/+ОБНОВИТЕ_ССЫЛКУ_В_АДМИНКЕ")
                    )

    # 2. Настраиваем главный целевой канал (-1003246253184)
    c.execute("SELECT value FROM settings WHERE key = 'target_link'")
    t_row = c.fetchone()
    if not t_row or "ВАША_ССЫЛКА" in t_row[0] or "ОБНОВИТЕ" in t_row[0]:
        try:
            target_chat = await bot.get_chat(int(TARGET_CHANNEL_ID))
            t_link = await bot.create_chat_invite_link(
                chat_id=int(TARGET_CHANNEL_ID),
                name="Доступ из бота",
                creates_join_request=True
            )
            c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('target_link', ?)", (t_link.invite_link,))
            print(f"🎁 Главный канал подключен: «{target_chat.title}» ({TARGET_CHANNEL_ID}) -> {t_link.invite_link}")
        except Exception as e:
            print(f"⚠️ ВНИМАНИЕ: Не удалось автоматически создать ссылку для главного канала {TARGET_CHANNEL_ID}: {e}")
            if not t_row:
                c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('target_link', 'https://t.me/+ОБНОВИТЕ_ССЫЛКУ_В_АДМИНКЕ')")

    conn.commit()
    conn.close()

def register_user(user_id: int, username: str, full_name: str):
    conn = sqlite3.connect("funnel_bot.db")
    c = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    c.execute("""
        INSERT INTO users (user_id, username, full_name, joined_date)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            username = excluded.username,
            full_name = excluded.full_name
    """, (user_id, username or "Нет_юзернейма", full_name, now))
    conn.commit()
    conn.close()

def get_user(user_id: int):
    conn = sqlite3.connect("funnel_bot.db")
    c = conn.cursor()
    c.execute("SELECT user_id, username, full_name, status, joined_date FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row

def set_user_status(user_id: int, status: str):
    conn = sqlite3.connect("funnel_bot.db")
    c = conn.cursor()
    c.execute("UPDATE users SET status = ? WHERE user_id = ?", (status, user_id))
    conn.commit()
    conn.close()

def record_join_request(user_id: int, chat_id: str):
    conn = sqlite3.connect("funnel_bot.db")
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO user_requests (user_id, chat_id) VALUES (?, ?)", (user_id, str(chat_id)))
    conn.commit()
    conn.close()

def has_requested_or_joined(user_id: int, chat_id: str) -> bool:
    conn = sqlite3.connect("funnel_bot.db")
    c = conn.cursor()
    c.execute("SELECT 1 FROM user_requests WHERE user_id = ? AND chat_id = ?", (user_id, str(chat_id)))
    row = c.fetchone()
    conn.close()
    return row is not None

def get_sponsors():
    conn = sqlite3.connect("funnel_bot.db")
    c = conn.cursor()
    c.execute("SELECT id, chat_id, title, invite_link FROM sponsors")
    rows = c.fetchall()
    conn.close()
    return rows

def add_sponsor(chat_id: str, title: str, invite_link: str):
    conn = sqlite3.connect("funnel_bot.db")
    c = conn.cursor()
    c.execute(
        "INSERT OR REPLACE INTO sponsors (chat_id, title, invite_link) VALUES (?, ?, ?)",
        (str(chat_id).strip(), title.strip(), invite_link.strip())
    )
    conn.commit()
    conn.close()

def delete_sponsor(sponsor_id: int):
    conn = sqlite3.connect("funnel_bot.db")
    c = conn.cursor()
    c.execute("DELETE FROM sponsors WHERE id = ?", (sponsor_id,))
    conn.commit()
    conn.close()

def get_target_link() -> str:
    conn = sqlite3.connect("funnel_bot.db")
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key = 'target_link'")
    row = c.fetchone()
    conn.close()
    return row[0] if row else "Ссылка еще не настроена"

def set_target_link(link: str):
    conn = sqlite3.connect("funnel_bot.db")
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('target_link', ?)", (link.strip(),))
    conn.commit()
    conn.close()

# =====================================================================
# 3. ЛОГИКА ПРОВЕРКИ ЗАЯВОК В 3 КАНАЛА
# =====================================================================
def build_sponsors_kb():
    sponsors = get_sponsors()
    kb = InlineKeyboardBuilder()
    for sp_id, chat_id, title, link in sponsors:
        kb.button(text=f"🔒 Подать заявку: {title}", url=link)
    kb.button(text="✅ Я подал заявки во все каналы", callback_data="check_requests")
    kb.adjust(1)
    return kb.as_markup()

async def check_user_all_channels(user_id: int):
    sponsors = get_sponsors()
    missing_channels = []

    for sp_id, chat_id, title, link in sponsors:
        # 1. Проверяем, зафиксировал ли бот подачу заявки в базу
        if has_requested_or_joined(user_id, chat_id):
            continue

        # 2. Проверяем, не состоит ли человек уже внутри канала (если ты его уже принял)
        try:
            member = await bot.get_chat_member(chat_id=int(chat_id), user_id=user_id)
            if member.status in ("member", "administrator", "creator"):
                record_join_request(user_id, str(chat_id))
                continue
        except Exception as e:
            print(f"[Ошибка проверки канала {title} ({chat_id})]: {e}")

        missing_channels.append(title)

    return missing_channels

# =====================================================================
# 4. ПЕРЕХВАТ ЗАЯВОК В ЗАКРЫТЫЕ КАНАЛЫ (БЕЗ АВТООДОБРЕНИЯ!)
# =====================================================================
@dp.chat_join_request()
async def on_sponsor_join_request(update: types.ChatJoinRequest):
    """
    Когда человек подает заявку в любой из твоих закрытых каналов,
    бот НЕ принимает его, а записывает в базу факт подачи заявки.
    """
    user_id = update.from_user.id
    chat_id = str(update.chat.id)
    register_user(user_id, update.from_user.username, update.from_user.full_name)
    record_join_request(user_id, chat_id)
    print(f"[ЗАЯВКА ЗАФИКСИРОВАНА] Юзер {user_id} (@{update.from_user.username}) подал заявку в {update.chat.title} ({chat_id})")

# =====================================================================
# 5. ПОЛЬЗОВАТЕЛЬСКИЕ ХЕНДЛЕРЫ
# =====================================================================
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    register_user(user_id, message.from_user.username, message.from_user.full_name)
    user = get_user(user_id)

    if user and user[3] == "approved":
        link = get_target_link()
        await message.answer(
            f"✅ <b>Ваша заявка уже одобрена!</b>\n\n"
            f"Вот ваша ссылка на закрытый канал:\n👉 {link}",
            parse_mode="HTML"
        )
        return

    if user and user[3] == "waiting":
        await message.answer(
            "⏳ <b>Ваша заявка находится на рассмотрении.</b>\n"
            "Вы подали заявки во все каналы! Ссылку на целевой канал отправят вам в ближайшее время.",
            parse_mode="HTML"
        )
        return

    text = (
        f"👋 Привет, <b>{message.from_user.first_name}</b>!\n\n"
        "Чтобы получить ссылку на закрытый канал, вам нужно <b>подать заявки на вступление</b> в 3 наших приватных канала ниже.\n\n"
        "👇 Перейдите по каждой кнопке, нажмите <b>«Подать заявку»</b>, а затем вернитесь сюда и нажмите <b>«✅ Я подал заявки во все каналы»</b>:"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=build_sponsors_kb())

@dp.callback_query(F.data == "check_requests")
async def cb_check_requests(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    register_user(user_id, callback.from_user.username, callback.from_user.full_name)
    sponsors = get_sponsors()

    missing = await check_user_all_channels(user_id)

    if missing:
        missing_str = "\n• ".join(missing)
        await callback.answer(
            "❌ Нужно подписаться (подать заявку) на ВСЕ каналы!",
            show_alert=True
        )
        await callback.message.answer(
            f"⚠️ <b>Вы подали заявки не во все каналы!</b>\n\n"
            f"Для получения доступа осталось подать заявку в:\n• <b>{missing_str}</b>\n\n"
            f"Нажмите на кнопки каналов выше, подайте заявки и снова нажмите кнопку проверки.",
            parse_mode="HTML"
        )
        return

    user = get_user(user_id)
    if user and user[3] == "approved":
        await callback.message.edit_text(f"✅ Ваша ссылка: {get_target_link()}")
        return

    set_user_status(user_id, "waiting")

    await callback.message.edit_text(
        "✅ <b>Проверка пройдена! Вы подали заявки во все каналы.</b>\n\n"
        "⏳ <b>Ваша заявка на рассмотрении!</b>\n"
        "Ссылку на закрытый канал отправят вам сюда в ближайшее время.",
        parse_mode="HTML"
    )

    # Отправляем уведомление тебе (админу) с кнопкой выдачи ссылки
    adm_kb = InlineKeyboardBuilder()
    adm_kb.button(text="✅ Одобрить и выслать ссылку", callback_data=f"approve_user_{user_id}")
    adm_kb.button(text="❌ Отклонить", callback_data=f"reject_user_{user_id}")
    adm_kb.adjust(1)

    username_str = f"@{callback.from_user.username}" if callback.from_user.username else "Без юзернейма"
    try:
        await bot.send_message(
            ADMIN_ID,
            f"🔔 <b>Пользователь выполнил условия!</b>\n\n"
            f"👤 Имя: <b>{callback.from_user.full_name}</b> ({username_str})\n"
            f"🆔 ID: <code>{user_id}</code>\n"
            f"✅ Подал заявки во все {len(sponsors)} канала.\n\n"
            f"Нажмите кнопку ниже, чтобы бот отправил ему ссылку на канал <code>{TARGET_CHANNEL_ID}</code>:",
            parse_mode="HTML",
            reply_markup=adm_kb.as_markup()
        )
    except Exception as e:
        print(f"Ошибка уведомления админа: {e}")

# =====================================================================
# 6. АДМИН-ПАНЕЛЬ (/admin)
# =====================================================================
class AdminStates(StatesGroup):
    waiting_for_sponsor = State()
    waiting_for_target_link = State()

def admin_menu_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="⏳ Ожидают ссылку (На рассмотрении)", callback_data="adm_waiting_list")
    kb.button(text="✅ Одобрить всех ожидающих разом", callback_data="adm_approve_all")
    kb.button(text="🔄 Пересоздать ссылки для моих 4 каналов", callback_data="adm_regen_links")
    kb.button(text="📊 Статистика", callback_data="adm_stats")
    kb.button(text="📋 Управление каналами-спонсорами", callback_data="adm_sponsors")
    kb.button(text="🔗 Изменить главную ссылку вручную", callback_data="adm_set_link")
    kb.adjust(1)
    return kb.as_markup()

@dp.message(Command("admin"))
async def cmd_admin(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.clear()
    link = get_target_link()
    await message.answer(
        f"🛠 <b>Панель администратора</b>\n\n"
        f"🎯 Главный канал (приз): <code>{TARGET_CHANNEL_ID}</code>\n"
        f"🔗 Выдаваемая ссылка:\n<code>{link}</code>\n\n"
        f"Выберите действие:",
        parse_mode="HTML",
        reply_markup=admin_menu_kb()
    )

@dp.callback_query(F.data == "adm_regen_links")
async def cb_adm_regen_links(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    # Очищаем старые заглушки и заново генерируем инвайт-ссылки через API
    conn = sqlite3.connect("funnel_bot.db")
    c = conn.cursor()
    c.execute("DELETE FROM sponsors")
    c.execute("DELETE FROM settings WHERE key = 'target_link'")
    conn.commit()
    conn.close()

    await auto_setup_channels()
    link = get_target_link()
    await callback.answer("✅ Ссылки и названия всех 4 каналов успешно обновлены!", show_alert=True)
    await callback.message.edit_text(
        f"🛠 <b>Панель администратора (Ссылки обновлены!)</b>\n\n"
        f"🎯 Главный канал: <code>{TARGET_CHANNEL_ID}</code>\n"
        f"🔗 Выдаваемая ссылка:\n<code>{link}</code>",
        parse_mode="HTML",
        reply_markup=admin_menu_kb()
    )

@dp.callback_query(F.data.startswith("approve_user_"))
async def cb_approve_user(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    target_id = int(callback.data.split("_")[2])
    set_user_status(target_id, "approved")
    link = get_target_link()

    try:
        await bot.send_message(
            target_id,
            f"🎉 <b>Ваша заявка рассмотрена и одобрена!</b>\n\n"
            f"Вот ваша пригласительная ссылка в закрытый канал:\n👉 {link}",
            parse_mode="HTML"
        )
        await callback.message.edit_text(
            callback.message.text + f"\n\n✅ <b>ОДОБРЕНО: Ссылка отправлена пользователю {target_id}!</b>",
            parse_mode="HTML"
        )
    except Exception as e:
        await callback.message.edit_text(
            callback.message.text + f"\n\n⚠️ Ошибка отправки пользователю: {e}",
            parse_mode="HTML"
        )

@dp.callback_query(F.data.startswith("reject_user_"))
async def cb_reject_user(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    target_id = int(callback.data.split("_")[2])
    set_user_status(target_id, "new")
    try:
        await bot.send_message(
            target_id,
            "❌ Ваша заявка отклонена. Проверьте, что вы подали заявки во все каналы, и нажмите /start."
        )
    except Exception:
        pass
    await callback.message.edit_text(callback.message.text + "\n\n❌ <b>ОТКЛОНЕНО</b>", parse_mode="HTML")

@dp.callback_query(F.data == "adm_waiting_list")
async def cb_adm_waiting_list(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    conn = sqlite3.connect("funnel_bot.db")
    c = conn.cursor()
    c.execute("SELECT user_id, username, full_name FROM users WHERE status = 'waiting' LIMIT 15")
    rows = c.fetchall()
    conn.close()

    kb = InlineKeyboardBuilder()
    if not rows:
        text = "⏳ <b>Сейчас нет пользователей на рассмотрении.</b>"
    else:
        lines = ["⏳ <b>Пользователи на рассмотрении:</b>\n<i>Нажмите на кнопку, чтобы отправить человеку ссылку на главный канал:</i>\n"]
        for uid, uname, fname in rows:
            lines.append(f"• {fname} (@{uname}) — ID: <code>{uid}</code>")
            kb.button(text=f"✅ Отправить ссылку: {fname}", callback_data=f"approve_user_{uid}")
        text = "\n".join(lines)

    kb.button(text="🔙 Назад", callback_data="adm_back")
    kb.adjust(1)
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())

@dp.callback_query(F.data == "adm_approve_all")
async def cb_adm_approve_all(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    conn = sqlite3.connect("funnel_bot.db")
    c = conn.cursor()
    c.execute("SELECT user_id FROM users WHERE status = 'waiting'")
    rows = c.fetchall()
    conn.close()

    if not rows:
        await callback.answer("Список ожидающих пуст!", show_alert=True)
        return

    link = get_target_link()
    sent = 0
    for (uid,) in rows:
        set_user_status(uid, "approved")
        try:
            await bot.send_message(
                uid,
                f"🎉 <b>Ваша заявка рассмотрена и одобрена!</b>\n\n"
                f"Вот ваша пригласительная ссылка в закрытый канал:\n👉 {link}",
                parse_mode="HTML"
            )
            sent += 1
            await asyncio.sleep(0.05)
        except Exception:
            pass

    await callback.answer(f"✅ Ссылка отправлена {sent} пользователям!", show_alert=True)
    await cb_adm_stats(callback)

@dp.callback_query(F.data == "adm_stats")
async def cb_adm_stats(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    conn = sqlite3.connect("funnel_bot.db")
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    total = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM users WHERE status = 'waiting'")
    waiting = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM users WHERE status = 'approved'")
    approved = c.fetchone()[0]
    conn.close()

    text = (
        f"📊 <b>Статистика бота:</b>\n\n"
        f"👥 Всего запустили бота: <b>{total}</b>\n"
        f"⏳ Ждут одобрения (подали все 3 заявки): <b>{waiting}</b>\n"
        f"✅ Получили ссылку на главный канал: <b>{approved}</b>"
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=admin_menu_kb())

@dp.callback_query(F.data == "adm_sponsors")
async def cb_adm_sponsors(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    sponsors = get_sponsors()
    kb = InlineKeyboardBuilder()

    lines = ["📋 <b>Активные каналы-спонсоры:</b>\n"]
    for sp_id, chat_id, title, link in sponsors:
        lines.append(f"• <b>{title}</b> (<code>{chat_id}</code>)\n  Ссылка: {link}")
        kb.button(text=f"🗑 Удалить «{title}»", callback_data=f"del_sp_{sp_id}")
    text = "\n".join(lines) if sponsors else "Список пуст."

    kb.button(text="➕ Добавить еще канал", callback_data="adm_add_sponsor")
    kb.button(text="🔙 Назад", callback_data="adm_back")
    kb.adjust(1)
    await callback.message.edit_text(text, parse_mode="HTML", disable_web_page_preview=True, reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("del_sp_"))
async def cb_del_sponsor(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    sp_id = int(callback.data.split("_")[2])
    delete_sponsor(sp_id)
    await callback.answer("Канал удален!")
    await cb_adm_sponsors(callback)

@dp.callback_query(F.data == "adm_add_sponsor")
async def cb_adm_add_sponsor(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    await state.set_state(AdminStates.waiting_for_sponsor)
    await callback.message.answer(
        "Пришлите данные нового канала через черту <code>|</code>:\n"
        "<code>ID_канала | Название | Ссылка_с_заявкой</code>",
        parse_mode="HTML"
    )
    await callback.answer()

@dp.message(AdminStates.waiting_for_sponsor)
async def process_add_sponsor(message: types.Message, state: FSMContext):
    await state.clear()
    parts = [p.strip() for p in message.text.split("|")]
    if len(parts) != 3:
        await message.answer("⚠️ Нужно 3 параметра через <code>|</code>.", parse_mode="HTML", reply_markup=admin_menu_kb())
        return
    add_sponsor(parts[0], parts[1], parts[2])
    await message.answer(f"✅ Канал <b>{parts[1]}</b> сохранен!", parse_mode="HTML", reply_markup=admin_menu_kb())

@dp.callback_query(F.data == "adm_set_link")
async def cb_adm_set_link(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    await state.set_state(AdminStates.waiting_for_target_link)
    await callback.message.answer("🔗 Отправьте новую ссылку на главный канал:")
    await callback.answer()

@dp.message(AdminStates.waiting_for_target_link)
async def process_set_link(message: types.Message, state: FSMContext):
    await state.clear()
    set_target_link(message.text)
    await message.answer(f"✅ Ссылка обновлена:\n<code>{message.text}</code>", parse_mode="HTML", reply_markup=admin_menu_kb())

@dp.callback_query(F.data == "adm_back")
async def cb_adm_back(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    link = get_target_link()
    await callback.message.edit_text(
        f"🛠 <b>Панель администратора</b>\n\n🎯 Главный канал: <code>{TARGET_CHANNEL_ID}</code>\n🔗 Ссылка:\n<code>{link}</code>",
        parse_mode="HTML",
        reply_markup=admin_menu_kb()
    )

# =====================================================================
# 7. ЗАПУСК БОТА
# =====================================================================
async def main():
    init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    await auto_setup_channels()
    print("✅ Бот успешно запущен и готов проверять заявки в твои 3 канала!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())