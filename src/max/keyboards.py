from maxapi.types import CallbackButton, OpenAppButton
from maxapi.utils.inline_keyboard import InlineKeyboardBuilder


def items_keyboard(
    items: list[dict], callback_prefix: str, add_skip: bool = False, back_callback: str | None = None,
) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    for item in items:
        btn_id = item.get("id", item.get("name", ""))
        kb.row(CallbackButton(text=item["name"], payload=f"{callback_prefix}:{btn_id}"))
    if add_skip:
        kb.row(CallbackButton(text="\u23ed Пропустить", payload=f"{callback_prefix}:skip"))
    if back_callback:
        kb.row(CallbackButton(text="\u25c0 Назад", payload=back_callback))
    return kb


def grades_keyboard(
    grades: list[int], callback_prefix: str, back_callback: str | None = None,
) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    for g in grades:
        kb.add(CallbackButton(text=str(g), payload=f"{callback_prefix}:{g}"))
    kb.adjust(4)
    if back_callback:
        kb.row(CallbackButton(text="\u25c0 Назад", payload=back_callback))
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
    add_other: bool = False,
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

    if add_other:
        kb.row(CallbackButton(text="✏️ Другое", payload=f"{callback_prefix}:other"))

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


def search_pagination_keyboard(page: int, total_pages: int, level: int = 1) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    if total_pages > 1:
        nav_row = []
        if page > 1:
            nav_row.append(CallbackButton(text="\u25c0 Назад", payload=f"search:page:{page - 1}"))
        nav_row.append(CallbackButton(text=f"{page}/{total_pages}", payload="noop"))
        if page < total_pages:
            nav_row.append(CallbackButton(text="Далее \u25b6", payload=f"search:page:{page + 1}"))
        kb.row(*nav_row)
    if level < 3:
        kb.row(CallbackButton(text="\U0001f50d Расширить поиск", payload="search:expand"))
    kb.row(CallbackButton(text="\U0001f504 Новый поиск", payload="new_search"))
    return kb


def clarify_keyboard(options: list[dict], level: str) -> InlineKeyboardBuilder:
    """Build clarification keyboard from options.

    Each option: {"value": str, "display": str, "count": int}
    Callback: clarify:{level}:{index}
    """
    kb = InlineKeyboardBuilder()
    for i, opt in enumerate(options):
        kb.row(CallbackButton(text=opt["display"], payload=f"clarify:{level}:{i}"))
    kb.row(CallbackButton(text="\u25c0 Назад", payload="clarify:back"))
    return kb


def registration_keyboard(bot_username: str, bot_contact_id: int | None = None) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.row(OpenAppButton(
        text="Зарегистрироваться",
        web_app=bot_username,
        contact_id=bot_contact_id,
    ))
    return kb


def skip_keyboard() -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.row(CallbackButton(text="\u23ed Пропустить", payload="onb_skip"))
    return kb


def broadcast_consent_keyboard() -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.row(CallbackButton(text="Согласен", payload="broadcast_consent:yes"))
    kb.row(CallbackButton(text="Не согласен", payload="broadcast_consent:no"))
    return kb
