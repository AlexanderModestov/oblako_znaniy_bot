from maxapi.types import CallbackButton
from maxapi.utils.inline_keyboard import InlineKeyboardBuilder


def items_keyboard(items: list[dict], callback_prefix: str, add_skip: bool = False) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    for item in items:
        btn_id = item.get("id", item.get("name", ""))
        kb.row(CallbackButton(text=item["name"], payload=f"{callback_prefix}:{btn_id}"))
    if add_skip:
        kb.row(CallbackButton(text="\u23ed Пропустить", payload=f"{callback_prefix}:skip"))
    return kb


def grades_keyboard(grades: list[int], callback_prefix: str) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    for g in grades:
        kb.add(CallbackButton(text=str(g), payload=f"{callback_prefix}:{g}"))
    kb.adjust(4)
    return kb


def subjects_toggle_keyboard(subjects: list[dict], selected: set[int]) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    for s in subjects:
        mark = "\u2705" if s["id"] in selected else "\u2b1c"
        kb.row(CallbackButton(text=f"{mark} {s['name']}", payload=f"onb_subj:{s['id']}"))
    kb.row(CallbackButton(text="\u2714\ufe0f Готово", payload="onb_subj:done"))
    return kb


def pagination_keyboard(page: int, total_pages: int, callback_prefix: str) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    row = []
    if page > 1:
        row.append(CallbackButton(text="\u25c0 Назад", payload=f"{callback_prefix}:page:{page - 1}"))
    row.append(CallbackButton(text=f"{page}/{total_pages}", payload="noop"))
    if page < total_pages:
        row.append(CallbackButton(text="Далее \u25b6", payload=f"{callback_prefix}:page:{page + 1}"))
    kb.row(*row)
    kb.row(CallbackButton(text="\U0001f504 Новый поиск", payload="new_search"))
    return kb


def paginated_items_keyboard(
    items: list[dict], callback_prefix: str, page: int = 1, per_page: int = 8,
) -> InlineKeyboardBuilder:
    total_pages = max(1, -(-len(items) // per_page))
    page = max(1, min(page, total_pages))
    start = (page - 1) * per_page
    page_items = items[start : start + per_page]

    kb = InlineKeyboardBuilder()
    for item in page_items:
        btn_id = item.get("id", item.get("name", ""))
        kb.row(CallbackButton(text=item["name"], payload=f"{callback_prefix}:{btn_id}"))

    if total_pages > 1:
        nav_row = []
        if page > 1:
            nav_row.append(CallbackButton(text="\u25c0 Назад", payload=f"{callback_prefix}_page:{page - 1}"))
        nav_row.append(CallbackButton(text=f"{page}/{total_pages}", payload="noop"))
        if page < total_pages:
            nav_row.append(CallbackButton(text="Далее \u25b6", payload=f"{callback_prefix}_page:{page + 1}"))
        kb.row(*nav_row)

    return kb


def search_choice_keyboard() -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.row(CallbackButton(text="\U0001f50d Введите Ваш запрос", payload="search_text"))
    kb.row(CallbackButton(text="\U0001f4da Поиск по учебным планам", payload="search_curriculum"))
    return kb


def new_search_keyboard() -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.row(CallbackButton(text="\U0001f504 Новый поиск", payload="new_search"))
    return kb


def search_pagination_keyboard(page: int, total_pages: int) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    nav_row = []
    if page > 1:
        nav_row.append(CallbackButton(text="\u25c0 Назад", payload=f"search:page:{page - 1}"))
    nav_row.append(CallbackButton(text=f"{page}/{total_pages}", payload="noop"))
    if page < total_pages:
        nav_row.append(CallbackButton(text="Далее \u25b6", payload=f"search:page:{page + 1}"))
    kb.row(*nav_row)
    kb.row(CallbackButton(text="\U0001f504 Новый поиск", payload="new_search"))
    return kb


def skip_keyboard() -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.row(CallbackButton(text="\u23ed Пропустить", payload="onb_skip"))
    return kb
