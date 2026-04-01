from maxapi import F, Router
from maxapi.context import MemoryContext
from maxapi.types import MessageCallback
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.services.user import UserService
from src.max.keyboards import search_choice_keyboard

router = Router(router_id="max_menu")
user_service = UserService()

CONSENT_BLOCK_TEXT = (
    "Для использования поиска необходимо дать согласие на обработку персональных данных.\n\n"
    "Нажмите /start, чтобы получить запрос на согласие повторно."
)


@router.message_callback(F.callback.payload == "new_search")
async def new_search(event: MessageCallback, context: MemoryContext, session: AsyncSession):
    user = await user_service.get_by_max_user_id(session, event.callback.user.user_id)
    if user and not user.consent_given:
        await event.bot.edit_message(
            message_id=event.message.body.mid,
            text=CONSENT_BLOCK_TEXT,
        )
        return
    await context.clear()
    # Freeze the old message (remove keyboard), send new one
    await event.bot.edit_message(
        message_id=event.message.body.mid,
        text=event.message.body.text,
        attachments=[],
    )
    kb = search_choice_keyboard()
    await event.bot.send_message(
        chat_id=event.message.recipient.chat_id,
        text="Выберите способ поиска:",
        attachments=[kb.as_markup()],
    )


@router.message_callback(F.callback.payload == "search_text")
async def search_text(event: MessageCallback, context: MemoryContext, session: AsyncSession):
    user = await user_service.get_by_max_user_id(session, event.callback.user.user_id)
    if user and not user.consent_given:
        await event.bot.edit_message(
            message_id=event.message.body.mid,
            text=CONSENT_BLOCK_TEXT,
        )
        return
    await context.clear()
    # Freeze the old message (remove keyboard), send new one
    await event.bot.edit_message(
        message_id=event.message.body.mid,
        text=event.message.body.text,
        attachments=[],
    )
    await event.bot.send_message(
        chat_id=event.message.recipient.chat_id,
        text="Просто напишите, что вы ищете, и я найду подходящие уроки.",
    )


@router.message_callback(F.callback.payload == "noop")
async def noop(event: MessageCallback):
    await event.answer(notification="")
