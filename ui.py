"""Telegram menu and demonstration card rendering."""
from html import escape
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def kb(*rows: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=label, callback_data=data) for label, data in row]
        for row in rows
    ])


def main_menu(is_admin: bool) -> InlineKeyboardMarkup:
    rows = [
        [('Создать демо-карточку', 'ui:new')],
        [('Мои карточки', 'ui:cards'), ('Business', 'ui:business')],
        [('Мой ID', 'ui:id')],
    ]
    if is_admin:
        rows.append([('Админ-панель', 'adm:menu')])
    return kb(*rows)


def admin_menu(superadmin: bool) -> InlineKeyboardMarkup:
    rows = [
        [('Статистика', 'adm:stats'), ('Пользователи', 'adm:users')],
        [('Разрешить ID', 'adm:allow'), ('Запретить ID', 'adm:deny')],
        [('Заблокировать', 'adm:ban'), ('Разблокировать', 'adm:unban')],
    ]
    if superadmin:
        rows.append([('Назначить админа', 'adm:grant'), ('Снять админа', 'adm:revoke')])
    rows.append([('В меню', 'ui:home')])
    return kb(*rows)


def card_menu(card_id: int) -> InlineKeyboardMarkup:
    return kb(
        [('Принять (демо)', f'card:accept:{card_id}'),
         ('Отклонить', f'card:decline:{card_id}')],
        [('Как это работает?', f'card:help:{card_id}')],
        [('Мои карточки', 'ui:cards')]
    )


def card_text(gift: str, stars: int) -> str:
    stars_display = f'{stars:,}'.replace(',', ' ')
    return (
        '🧪 <b>ДЕМО / ТЕСТОВЫЙ ЭКРАН</b>\n\n'
        f'🎁 <b>Подарок:</b> {escape(gift)}\n'
        f'⭐ <b>Тестовые Stars:</b> {stars_display}\n\n'
        'Это демонстрация интерфейса. Здесь нет оплаты, реального обмена, '
        'начисления Stars или передачи NFT.'
    )
