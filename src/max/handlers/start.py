import logging

from maxapi import F, Router
from maxapi.context import MemoryContext, State, StatesGroup
from maxapi.types import BotStarted, MessageCallback, MessageCreated

from sqlalchemy.ext.asyncio import AsyncSession

from src.config import get_settings
from src.core.schemas import UserCreate
from src.core.services.user import UserService
from src.max.keyboards import (
    paginated_items_keyboard,
    registration_keyboard,
    search_choice_keyboard,
    skip_keyboard,
    subjects_toggle_keyboard,
)

router = Router(router_id="max_start")
user_service = UserService()
logger = logging.getLogger("max.start")


class OnboardingStates(StatesGroup):
    full_name = State()
    region = State()
    municipality = State()
    school = State()
    school_other = State()
    subjects = State()
    phone = State()
    email = State()


@router.bot_started()
async def on_bot_started(event: BotStarted, context: MemoryContext, session: AsyncSession):
    user = await user_service.get_by_max_user_id(session, event.user.user_id)
    if user:
        await context.clear()
        kb = search_choice_keyboard()
        await event.bot.send_message(
            chat_id=event.chat_id,
            text=f"С возвращением, {user.full_name}!\n\n"
                 "Выберите способ поиска:",
            attachments=[kb.as_markup()],
        )
        return
    settings = get_settings()
    if settings.web_app_url:
        kb = registration_keyboard(settings.web_app_url)
        await event.bot.send_message(
            chat_id=event.chat_id,
            text="Добро пожаловать! Для начала работы пройдите регистрацию:",
            attachments=[kb.as_markup()],
        )
        return
    await context.set_state(OnboardingStates.full_name)
    await event.bot.send_message(
        chat_id=event.chat_id,
        text="Добро пожаловать! Давайте зарегистрируемся.\n\n"
             "Введите ваше ФИО (Фамилия Имя Отчество) одним сообщением:",
    )


@router.message_created(F.message.body.text, OnboardingStates.full_name)
async def process_name(event: MessageCreated, context: MemoryContext, session: AsyncSession):
    name = event.message.body.text.strip()
    if len(name.split()) < 3:
        await event.message.answer("Пожалуйста, введите полное ФИО (Фамилия Имя Отчество) одним сообщением:")
        return
    await context.update_data(full_name=name)
    await context.set_state(OnboardingStates.region)
    regions = await user_service.get_all_regions(session)
    await context.update_data(all_regions=regions)
    kb = paginated_items_keyboard(regions, "onb_region")
    await event.message.answer("Выберите ваш регион:", attachments=[kb.as_markup()])


@router.message_callback(F.callback.payload.startswith("onb_region_page:"), OnboardingStates.region)
async def process_region_page(event: MessageCallback, context: MemoryContext):
    page = int(event.callback.payload.split(":")[1])
    data = await context.get_data()
    regions = data["all_regions"]
    kb = paginated_items_keyboard(regions, "onb_region", page=page)
    await event.bot.edit_message(
        message_id=event.message.body.mid,
        text="Выберите ваш регион:",
        attachments=[kb.as_markup()],
    )


@router.message_callback(F.callback.payload.startswith("onb_region:"), OnboardingStates.region)
async def process_region_select(event: MessageCallback, context: MemoryContext, session: AsyncSession):
    region_id = int(event.callback.payload.split(":")[1])
    await context.update_data(region_id=region_id)
    municipalities = await user_service.get_municipalities_by_region(session, region_id)
    if municipalities:
        await context.set_state(OnboardingStates.municipality)
        await context.update_data(all_municipalities=municipalities)
        kb = paginated_items_keyboard(municipalities, "onb_muni")
        await event.bot.edit_message(
            message_id=event.message.body.mid,
            text="Выберите муниципалитет:",
            attachments=[kb.as_markup()],
        )
    else:
        await context.set_state(OnboardingStates.school)
        schools = await user_service.get_schools_by_region(session, region_id)
        await context.update_data(all_schools=schools)
        kb = paginated_items_keyboard(schools, "onb_school", add_other=True)
        await event.bot.edit_message(
            message_id=event.message.body.mid,
            text="Выберите вашу школу:",
            attachments=[kb.as_markup()],
        )


@router.message_callback(F.callback.payload.startswith("onb_muni_page:"), OnboardingStates.municipality)
async def process_municipality_page(event: MessageCallback, context: MemoryContext):
    page = int(event.callback.payload.split(":")[1])
    data = await context.get_data()
    municipalities = data["all_municipalities"]
    kb = paginated_items_keyboard(municipalities, "onb_muni", page=page)
    await event.bot.edit_message(
        message_id=event.message.body.mid,
        text="Выберите муниципалитет:",
        attachments=[kb.as_markup()],
    )


@router.message_callback(F.callback.payload.startswith("onb_muni:"), OnboardingStates.municipality)
async def process_municipality_select(event: MessageCallback, context: MemoryContext, session: AsyncSession):
    muni_idx = int(event.callback.payload.split(":")[1])
    data = await context.get_data()
    region_id = data["region_id"]
    municipality = data["all_municipalities"][muni_idx]["name"]
    await context.set_state(OnboardingStates.school)
    schools = await user_service.get_schools_by_municipality(session, region_id, municipality)
    await context.update_data(all_schools=schools)
    kb = paginated_items_keyboard(schools, "onb_school", add_other=True)
    await event.bot.edit_message(
        message_id=event.message.body.mid,
        text="Выберите вашу школу:",
        attachments=[kb.as_markup()],
    )


@router.message_callback(F.callback.payload.startswith("onb_school_page:"), OnboardingStates.school)
async def process_school_page(event: MessageCallback, context: MemoryContext):
    page = int(event.callback.payload.split(":")[1])
    data = await context.get_data()
    schools = data["all_schools"]
    kb = paginated_items_keyboard(schools, "onb_school", page=page, add_other=True)
    await event.bot.edit_message(
        message_id=event.message.body.mid,
        text="Выберите вашу школу:",
        attachments=[kb.as_markup()],
    )


@router.message_callback(F.callback.payload == "onb_school:other", OnboardingStates.school)
async def process_school_other(event: MessageCallback, context: MemoryContext):
    await context.set_state(OnboardingStates.school_other)
    await event.bot.edit_message(
        message_id=event.message.body.mid,
        text="Введите название вашей школы:",
    )


@router.message_created(F.message.body.text, OnboardingStates.school_other)
async def process_school_other_text(event: MessageCreated, context: MemoryContext, session: AsyncSession):
    name = event.message.body.text.strip()
    if not name:
        await event.message.answer("Пожалуйста, введите название школы:")
        return
    data = await context.get_data()
    region_id = data["region_id"]
    school_id = await user_service.create_school(session, region_id, name)
    await context.update_data(school_id=school_id)
    await context.set_state(OnboardingStates.subjects)
    subjects = await user_service.get_all_subjects(session)
    await context.update_data(available_subjects=subjects, selected_subjects=[])
    kb = subjects_toggle_keyboard(subjects, set())
    await event.message.answer(
        "Какие предметы вы ведёте? Выберите и нажмите «Готово»:",
        attachments=[kb.as_markup()],
    )


@router.message_callback(F.callback.payload.startswith("onb_school:"), OnboardingStates.school)
async def process_school_select(event: MessageCallback, context: MemoryContext, session: AsyncSession):
    school_id = int(event.callback.payload.split(":")[1])
    await context.update_data(school_id=school_id)
    await context.set_state(OnboardingStates.subjects)
    subjects = await user_service.get_all_subjects(session)
    await context.update_data(available_subjects=subjects, selected_subjects=[])
    kb = subjects_toggle_keyboard(subjects, set())
    await event.bot.edit_message(
        message_id=event.message.body.mid,
        text="Какие предметы вы ведёте? Выберите и нажмите «Готово»:",
        attachments=[kb.as_markup()],
    )


@router.message_callback(F.callback.payload.startswith("onb_subj:"), OnboardingStates.subjects)
async def process_subject_toggle(event: MessageCallback, context: MemoryContext):
    value = event.callback.payload.split(":")[1]
    data = await context.get_data()
    selected = set(data.get("selected_subjects", []))
    subjects = data["available_subjects"]

    if value == "done":
        await context.update_data(subjects=list(selected))
        await context.set_state(OnboardingStates.phone)
        await event.bot.edit_message(
            message_id=event.message.body.mid,
            text="Поделитесь номером телефона:\n\nВведите номер вручную в формате +7XXXXXXXXXX:",
        )
        return

    subj_id = int(value)
    if subj_id in selected:
        selected.discard(subj_id)
    else:
        selected.add(subj_id)
    await context.update_data(selected_subjects=list(selected))
    kb = subjects_toggle_keyboard(subjects, selected)
    await event.bot.edit_message(
        message_id=event.message.body.mid,
        text="Какие предметы вы ведёте? Выберите и нажмите «Готово»:",
        attachments=[kb.as_markup()],
    )


@router.message_created(F.message.body.text, OnboardingStates.phone)
async def process_phone_text(event: MessageCreated, context: MemoryContext):
    phone = event.message.body.text.strip().replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    if not (phone.startswith("+7") and len(phone) == 12 and phone[1:].isdigit()):
        await event.message.answer("Введите номер в формате +7XXXXXXXXXX:")
        return
    await context.update_data(phone=phone)
    await event.message.answer("Номер получен.")
    await context.set_state(OnboardingStates.email)
    kb = skip_keyboard()
    await event.message.answer(
        "Введите email (или нажмите «Пропустить»):",
        attachments=[kb.as_markup()],
    )


@router.message_created(F.message.body.text, OnboardingStates.email)
async def process_email(event: MessageCreated, context: MemoryContext, session: AsyncSession):
    await context.update_data(email=event.message.body.text.strip())
    await _finish_onboarding(event, context, session, max_user_id=event.message.sender.user_id)


@router.message_callback(F.callback.payload == "onb_skip", OnboardingStates.email)
async def process_email_skip(event: MessageCallback, context: MemoryContext, session: AsyncSession):
    await _finish_onboarding(event, context, session, max_user_id=event.callback.user.user_id)


async def _finish_onboarding(event, context: MemoryContext, session, max_user_id: int):
    data = await context.get_data()
    try:
        user_data = UserCreate(
            max_user_id=max_user_id,
            full_name=data["full_name"],
            phone=data["phone"],
            email=data.get("email"),
            region_id=data["region_id"],
            school_id=data["school_id"],
            subjects=data.get("subjects", []),
        )
        await user_service.create_user(session, user_data)
    except Exception as e:
        logger.exception("Failed to create user")
        error_msg = "Ошибка при регистрации. Попробуйте позже или начните заново /start"
        if isinstance(event, MessageCreated):
            await event.message.answer(error_msg)
        else:
            await event.answer(new_text=error_msg)
        return
    await context.clear()
    kb = search_choice_keyboard()
    success_msg = "Регистрация завершена!\n\nВыберите способ поиска:"
    if isinstance(event, MessageCreated):
        await event.message.answer(success_msg, attachments=[kb.as_markup()])
    else:
        await event.answer(new_text=success_msg, new_attachments=[kb.as_markup()])
