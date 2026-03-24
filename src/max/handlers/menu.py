from maxapi import F, Router
from maxapi.context import MemoryContext
from maxapi.types import MessageCallback

from src.max.keyboards import search_choice_keyboard

router = Router(router_id="max_menu")


@router.message_callback(F.callback.payload == "new_search")
async def new_search(event: MessageCallback, context: MemoryContext):
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
async def search_text(event: MessageCallback, context: MemoryContext):
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
