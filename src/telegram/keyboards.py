from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)


def items_keyboard(
    items: list[dict], callback_prefix: str, add_skip: bool = False, back_callback: str | None = None,
) -> InlineKeyboardMarkup:
    buttons = []
    for item in items:
        btn_id = item.get("id", item.get("name", ""))
        buttons.append([
            InlineKeyboardButton(text=item["name"], callback_data=f"{callback_prefix}:{btn_id}")
        ])
    if add_skip:
        buttons.append([
            InlineKeyboardButton(text="\u23ed Пропустить", callback_data=f"{callback_prefix}:skip")
        ])
    if back_callback:
        buttons.append([
            InlineKeyboardButton(text="\u25c0 Назад", callback_data=back_callback)
        ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def grades_keyboard(
    grades: list[int], callback_prefix: str, back_callback: str | None = None,
) -> InlineKeyboardMarkup:
    buttons = []
    row = []
    for g in grades:
        row.append(InlineKeyboardButton(text=str(g), callback_data=f"{callback_prefix}:{g}"))
        if len(row) == 4:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    if back_callback:
        buttons.append([
            InlineKeyboardButton(text="\u25c0 Назад", callback_data=back_callback)
        ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def subjects_toggle_keyboard(subjects: list[dict], selected: set[int]) -> InlineKeyboardMarkup:
    buttons = []
    for s in subjects:
        mark = "\u2705" if s["id"] in selected else "\u2b1c"
        buttons.append([
            InlineKeyboardButton(text=f"{mark} {s['name']}", callback_data=f"onb_subj:{s['id']}")
        ])
    buttons.append([
        InlineKeyboardButton(text="\u2714\ufe0f Готово", callback_data="onb_subj:done")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def pagination_keyboard(page: int, total_pages: int, callback_prefix: str) -> InlineKeyboardMarkup:
    buttons = []
    row = []
    if page > 1:
        row.append(InlineKeyboardButton(text="\u25c0 Назад", callback_data=f"{callback_prefix}:page:{page - 1}"))
    row.append(InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="noop"))
    if page < total_pages:
        row.append(InlineKeyboardButton(text="Далее \u25b6", callback_data=f"{callback_prefix}:page:{page + 1}"))
    buttons.append(row)
    buttons.append([
        InlineKeyboardButton(text="\U0001f504 Новый поиск", callback_data="new_search")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def paginated_items_keyboard(
    items: list[dict], callback_prefix: str, page: int = 1, per_page: int = 8,
    add_other: bool = False,
) -> InlineKeyboardMarkup:
    total_pages = max(1, -(-len(items) // per_page))  # ceil division
    page = max(1, min(page, total_pages))
    start = (page - 1) * per_page
    page_items = items[start : start + per_page]

    buttons = []
    for item in page_items:
        btn_id = item.get("id", item.get("name", ""))
        buttons.append([
            InlineKeyboardButton(text=item["name"], callback_data=f"{callback_prefix}:{btn_id}")
        ])

    if total_pages > 1:
        nav_row = []
        if page > 1:
            nav_row.append(InlineKeyboardButton(text="\u25c0 Назад", callback_data=f"{callback_prefix}_page:{page - 1}"))
        nav_row.append(InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="noop"))
        if page < total_pages:
            nav_row.append(InlineKeyboardButton(text="Далее \u25b6", callback_data=f"{callback_prefix}_page:{page + 1}"))
        buttons.append(nav_row)

    if add_other:
        buttons.append([
            InlineKeyboardButton(text="✏️ Другое", callback_data=f"{callback_prefix}:other")
        ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def search_pagination_keyboard(page: int, total_pages: int) -> InlineKeyboardMarkup:
    buttons = []
    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton(text="\u25c0 Назад", callback_data=f"search:page:{page - 1}"))
    nav_row.append(InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="noop"))
    if page < total_pages:
        nav_row.append(InlineKeyboardButton(text="Далее \u25b6", callback_data=f"search:page:{page + 1}"))
    buttons.append(nav_row)
    buttons.append([
        InlineKeyboardButton(text="\U0001f504 Новый поиск", callback_data="new_search")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def clarify_keyboard(options: list[dict], level: str) -> InlineKeyboardMarkup:
    """Build clarification keyboard from options.

    Each option: {"value": str, "display": str, "count": int}
    Callback: clarify:{level}:{index}
    """
    buttons = []
    for i, opt in enumerate(options):
        buttons.append([
            InlineKeyboardButton(text=opt["display"], callback_data=f"clarify:{level}:{i}")
        ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def search_choice_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="\U0001f50d Введите Ваш запрос", callback_data="search_text")],
        [InlineKeyboardButton(text="\U0001f4da Поиск по учебным планам", callback_data="search_curriculum")],
    ])


def new_search_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="\U0001f504 Новый поиск", callback_data="new_search")],
    ])


def contact_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="\U0001f4f1 Отправить контакт", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def skip_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="\u23ed Пропустить", callback_data="onb_skip")]
    ])


def broadcast_consent_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Согласен", callback_data="broadcast_consent:yes")],
        [InlineKeyboardButton(text="Не согласен", callback_data="broadcast_consent:no")],
    ])
