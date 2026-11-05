"""Opt-in NFT gift showcase. No payments, gift transfers or fake payouts."""
import asyncio
import logging
from html import escape
from pathlib import Path

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BusinessConnection, CallbackQuery, FSInputFile, Message

from .config import Settings
from .storage import Storage
from .ui import admin_menu, card_menu, card_text, kb, main_menu

settings = Settings.from_env()
db = Storage(settings.database_url)
router = Router()


class CreateCard(StatesGroup):
    gift = State()
    stars = State()
    photo = State()


class ManageUser(StatesGroup):
    user_id = State()


ADMIN_ACTIONS = {
    'allow': ('approved', True, 'Доступ разрешён'),
    'deny': ('approved', False, 'Доступ отключён'),
    'ban': ('banned', True, 'Пользователь заблокирован'),
    'unban': ('banned', False, 'Пользователь разблокирован'),
    'grant': ('admin', True, 'Права администратора выданы'),
    'revoke': ('admin', False, 'Права администратора сняты'),
}


def superadmin(user_id: int) -> bool:
    return user_id in settings.admin_ids


async def permissions(user_id: int) -> tuple[bool, bool]:
    user = await db.user(user_id)
    if superadmin(user_id):
        return True, True
    if user is None or user.banned:
        return False, False
    return user.approved or user.admin, user.admin


async def check_message(message: Message) -> bool:
    if not message.from_user:
        return False
    await db.touch(message.from_user.id, message.from_user.username)
    ok, _ = await permissions(message.from_user.id)
    if not ok:
        await message.answer('Доступ к демо не выдан. Сообщите администратору ваш ID: '
                             f'<code>{message.from_user.id}</code>')
    return ok


async def check_callback(callback: CallbackQuery) -> bool:
    await db.touch(callback.from_user.id, callback.from_user.username)
    ok, _ = await permissions(callback.from_user.id)
    if not ok:
        await callback.answer('Нет доступа или аккаунт заблокирован.', show_alert=True)
    return ok


async def open_home(message: Message, user_id: int):
    _, is_admin = await permissions(user_id)
    await message.answer(
        '<b>NFT Gift Showcase — DEMO</b>\n'
        'Создание тестовых карточек подарков и Stars. Реальные активы не используются.',
        reply_markup=main_menu(is_admin),
    )


@router.message(CommandStart())
async def on_start(message: Message, state: FSMContext):
    await state.clear()
    if await check_message(message):
        await open_home(message, message.from_user.id)


@router.message(Command('id'))
async def on_id(message: Message):
    if message.from_user:
        await db.touch(message.from_user.id, message.from_user.username)
        await message.answer(f'Ваш Telegram ID: <code>{message.from_user.id}</code>')


@router.message(Command('cancel'))
async def on_cancel(message: Message, state: FSMContext):
    await state.clear()
    if await check_message(message):
        await open_home(message, message.from_user.id)


@router.message(Command('new'))
async def on_new(message: Message, state: FSMContext):
    if not await check_message(message):
        return
    await state.set_state(CreateCard.gift)
    await message.answer(
        'Введите название любого подарка или ссылку вида <code>https://t.me/nft/...</code>.\n'
        'Название используется только как подпись к демонстрации.\n'
        'Отменить: /cancel'
    )


@router.message(CreateCard.gift)
async def new_gift(message: Message, state: FSMContext):
    if not await check_message(message):
        await state.clear()
        return
    gift = (message.text or '').strip()
    if not 1 <= len(gift) <= 160 or '\n' in gift or gift.startswith('/'):
        await message.answer('Введите название или ссылку длиной 1–160 символов в одну строку.')
        return
    await state.update_data(gift=gift)
    await state.set_state(CreateCard.stars)
    await message.answer('Введите любое положительное количество <b>тестовых</b> Stars '
                         '(до 9 223 372 036 854 775 807). /cancel — отмена.')


@router.message(CreateCard.stars)
async def new_stars(message: Message, state: FSMContext):
    if not await check_message(message):
        await state.clear()
        return
    raw = (message.text or '').replace(' ', '').strip()
    if not raw.isascii() or not raw.isdecimal() or len(raw) > 19:
        await message.answer('Введите положительное целое число до 9 223 372 036 854 775 807.')
        return
    stars = int(raw)
    if not 1 <= stars <= 9_223_372_036_854_775_807:
        await message.answer('Значение должно быть от 1 до 9 223 372 036 854 775 807.')
        return
    await state.update_data(stars=stars)
    await state.set_state(CreateCard.photo)
    await message.answer(
        'Пришлите фото подарка для карточки или напишите «пропустить» '
        'для стандартной демо-картинки. /cancel — отмена.')


@router.message(CreateCard.photo)
async def new_photo(message: Message, state: FSMContext):
    if not await check_message(message):
        await state.clear()
        return
    photo = None
    if message.photo:
        photo = message.photo[-1].file_id
    elif (message.text or '').strip().casefold() != 'пропустить':
        await message.answer('Пришлите изображение как фото или напишите «пропустить».')
        return
    data = await state.get_data()
    card = await db.create_card(message.from_user.id, data['gift'], data['stars'], photo_file_id=photo)
    await db.event(message.from_user.id, 'card_create')
    await state.clear()
    await message.answer('Карточка создана. Предпросмотр:')
    await send_card(message, card.id)


async def send_card(message: Message, card_id: int):
    card = await db.card_view(card_id)
    if card is None:
        await message.answer('Карточка не найдена.')
        return
    picture = card.photo_file_id or FSInputFile(
        Path(__file__).resolve().parent.parent / "assets" / "demo_gift.png")
    await message.answer_photo(
        picture, caption=card_text(card.gift, card.stars),
        reply_markup=card_menu(card.id),
    )


@router.message(Command('admin'))
async def on_admin(message: Message, state: FSMContext):
    if not await check_message(message):
        return
    ok, is_admin = await permissions(message.from_user.id)
    if ok and is_admin:
        await state.clear()
        await message.answer('Панель администратора',
                             reply_markup=admin_menu(superadmin(message.from_user.id)))
    else:
        await message.answer('Недостаточно прав.')


@router.callback_query(F.data.startswith('ui:'))
async def on_ui(callback: CallbackQuery, state: FSMContext):
    if not await check_callback(callback):
        return
    action = callback.data.split(':', 1)[1]
    uid = callback.from_user.id
    await callback.answer()
    if action == 'home':
        await state.clear()
        await open_home(callback.message, uid)
    elif action == 'new':
        await state.set_state(CreateCard.gift)
        await callback.message.answer('Название подарка или ссылка t.me/nft/...? /cancel — отмена.')
    elif action == 'cards':
        cards = await db.cards_by(uid)
        if not cards:
            await callback.message.answer('Карточек ещё нет.',
                                          reply_markup=kb([('Создать', 'ui:new')]))
        else:
            await callback.message.answer(
                'Ваши последние карточки:', reply_markup=kb(*[
                    [(f'#{c.id}: {c.gift[:30]} | {c.stars:,} тест. Stars', f'card:view:{c.id}')]
                    for c in cards
                ]))
    elif action == 'id':
        await callback.message.answer(f'Ваш Telegram ID: <code>{uid}</code>')
    elif action == 'business':
        links = await db.business_for(uid)
        status = '\n'.join('• ' + ('Подключён' if x.enabled else 'Отключён')
                           for x in links) or 'Подключений пока нет.'
        await callback.message.answer(
            '<b>Telegram Business</b>\n'
            'Подключите бота в настройках Telegram Business. Он не начинает переписки '
            'с контактами и отвечает только на входящую команду «демо» в разрешённом чате.\n\n'
            + status)


@router.callback_query(F.data.startswith('card:'))
async def on_card(callback: CallbackQuery):
    if not await check_callback(callback):
        return
    try:
        _, action, number = callback.data.split(':', 2)
        card_id = int(number)
    except (ValueError, AttributeError):
        await callback.answer('Неверная карточка.', show_alert=True)
        return
    card = await db.card(card_id)
    if card is None or card.owner_id != callback.from_user.id:
        await callback.answer('Карточка не найдена.', show_alert=True)
        return
    await callback.answer()
    if action == 'view':
        await send_card(callback.message, card_id)
    elif action == 'help':
        await db.event(callback.from_user.id, 'demo_help')
        await callback.message.answer(
            '<b>Как работает демо?</b>\n'
            '«Принять» только фиксирует тестовый выбор. «Отклонить» закрывает карточку.\n'
            'NFT и Stars не переводятся. Ссылка или имя подарка — это только текстовая подпись.')
    elif action == 'accept':
        await db.event(callback.from_user.id, 'demo_accept')
        await callback.message.edit_caption(
            caption='🧪 <b>ДЕМО: тестовый выбор «Принять» сохранён.</b>\n'
            'Никакие NFT или Stars не передавались.',
            reply_markup=kb([('Мои карточки', 'ui:cards')]))
    elif action == 'decline':
        await db.event(callback.from_user.id, 'demo_decline')
        await callback.message.edit_caption(caption='Демо-карточка закрыта.',
                                         reply_markup=kb([('Мои карточки', 'ui:cards')]))


@router.callback_query(F.data.startswith('adm:'))
async def on_admin_button(callback: CallbackQuery, state: FSMContext):
    if not await check_callback(callback):
        return
    _, is_admin = await permissions(callback.from_user.id)
    if not is_admin:
        await callback.answer('Недостаточно прав.', show_alert=True)
        return
    action = callback.data.split(':', 1)[1]
    if action in ('grant', 'revoke') and not superadmin(callback.from_user.id):
        await callback.answer('Только главный администратор.', show_alert=True)
        return
    await callback.answer()
    if action == 'menu':
        await state.clear()
        await callback.message.answer('Панель администратора',
                                       reply_markup=admin_menu(superadmin(callback.from_user.id)))
    elif action == 'stats':
        stats = await db.stats()
        labels = {'users': 'Всего пользователей', 'approved': 'С доступом',
                  'banned': 'Заблокированы', 'admins': 'Назначенные администраторы',
                  'cards': 'Карточки', 'views': 'Просмотры карточек',
                  'business': 'Активные Business-подключения',
                  'demo_accepts': 'Тестовые принятия',
                  'business_requests': 'Business демо-запросы'}
        await callback.message.answer('<b>Статистика</b>\n' + '\n'.join(
            f'{labels[k]}: <b>{v}</b>' for k, v in stats.items()))
    elif action == 'users':
        users = await db.latest_users()
        lines = []
        for u in users:
            flags = ('A' if u.admin or superadmin(u.id) else '-') + ('+' if u.approved else '-') + ('B' if u.banned else '-')
            lines.append(f'<code>{u.id}</code> {escape(u.username or "")} [{flags}]')
        await callback.message.answer(
            '<b>Последние пользователи</b>\n[A: админ, +: доступ, B: бан]\n'
            + ('\n'.join(lines) or 'Нет данных'))
    elif action in ADMIN_ACTIONS:
        await state.set_state(ManageUser.user_id)
        await state.update_data(action=action)
        await callback.message.answer(
            f'Действие: <b>{action}</b>. Пришлите числовой Telegram ID. /cancel — отмена.')


@router.message(ManageUser.user_id)
async def manage_user(message: Message, state: FSMContext):
    if not await check_message(message):
        await state.clear()
        return
    _, is_admin = await permissions(message.from_user.id)
    if not is_admin:
        await state.clear()
        await message.answer('Нет прав.')
        return
    raw = (message.text or '').strip()
    if not raw.isascii() or not raw.isdecimal():
        await message.answer('Нужен положительный числовой Telegram ID.')
        return
    user_id = int(raw)
    if user_id < 1 or user_id > 9223372036854775807:
        await message.answer('ID вне допустимого диапазона.')
        return
    data = await state.get_data()
    action = data.get('action')
    if action not in ADMIN_ACTIONS:
        await state.clear()
        await message.answer('Действие устарело.')
        return
    if action in ('grant', 'revoke') and not superadmin(message.from_user.id):
        await state.clear()
        await message.answer('Нет полномочий.')
        return
    if superadmin(user_id) and action in ('deny', 'ban', 'revoke'):
        await state.clear()
        await message.answer('Нельзя ограничивать главного администратора.')
        return
    if action in ('deny', 'ban'):
        target = await db.user(user_id)
        if target and target.admin and not superadmin(message.from_user.id):
            await state.clear()
            await message.answer('Назначенного администратора может ограничить только главный администратор.')
            return
    flag, value, result_text = ADMIN_ACTIONS[action]
    await db.set_flag(user_id, flag, value)
    await db.event(message.from_user.id, 'admin_' + action)
    await state.clear()
    await message.answer(f'{result_text}: <code>{user_id}</code>',
                         reply_markup=admin_menu(superadmin(message.from_user.id)))


@router.business_connection()
async def on_business_connection(connection: BusinessConnection):
    """Track connections; never initiate unsolicited messages."""
    await db.update_business(connection.id, connection.user.id, connection.is_enabled)
    logging.info('Business connection state updated for account %s', connection.user.id)


@router.business_message(F.text)
async def on_business_message(message: Message):
    """Explicit keyword opt-in, with no Stars payout or gift-transfer action."""
    if not message.business_connection_id or not message.from_user:
        return
    if (message.text or '').strip().casefold() not in ('демо', '/demo'):
        return
    link = await db.business(message.business_connection_id)
    if link is None or not link.enabled:
        return
    allowed, _ = await permissions(link.owner_id)
    if not allowed:
        return
    await db.event(link.owner_id, 'business_demo_request')
    try:
        await message.answer(
            '🧪 ДЕМО NFT Gift Showcase\n\n'
            'Это тестовый экран. Реальные подарки, переводы и начисления '
            'Telegram Stars здесь не используются.\n'
            'Для управления тестовыми карточками откройте сам бот.')
    except Exception:
        logging.exception('Cannot reply to Business chat (permissions or 24-hour window)')


@router.message()
async def fallback(message: Message):
    if await check_message(message):
        await message.answer('Выберите действие в меню. /start — меню, /new — новая карточка, '
                             '/admin — панель, /cancel — отмена.')


async def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    await db.init()
    bot = Bot(token=settings.token, default=DefaultBotProperties(parse_mode='HTML'))
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    try:
        await bot.delete_webhook(drop_pending_updates=False)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()
        await db.close()


if __name__ == '__main__':
    asyncio.run(main())
