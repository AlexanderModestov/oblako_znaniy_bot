import logging

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    ReplyKeyboardRemove,
    WebAppInfo,
)

from src.config import get_settings
from src.core.schemas import UserCreate
from src.core.services.user import UserService
from src.telegram.keyboards import (
    contact_keyboard,
    items_keyboard,
    paginated_items_keyboard,
    search_choice_keyboard,
    skip_keyboard,
    subjects_toggle_keyboard,
)

router = Router()
user_service = UserService()
logger = logging.getLogger(__name__)


class OnboardingStates(StatesGroup):
    full_name = State()
    region = State()
    municipality = State()
    school = State()
    school_other = State()
    subjects = State()
    phone = State()
    email = State()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, session):
    user = await user_service.get_by_telegram_id(session, message.from_user.id)
    if user:
        await state.clear()
        await message.answer(
            f"С возвращением, {user.full_name}!\n\n"
            "Выберите способ поиска:",
            reply_markup=search_choice_keyboard(),
        )
        return

    settings = get_settings()
    if settings.web_app_url:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="Зарегистрироваться",
                web_app=WebAppInfo(url=settings.web_app_url),
            )]
        ])
        await message.answer(
            "Добро пожаловать! Для начала работы пройдите регистрацию:",
            reply_markup=keyboard,
        )
        return

    await state.set_state(OnboardingStates.full_name)
    await message.answer(
        "Добро пожаловать! Давайте зарегистрируемся.\n\n"
        "Введите ваше ФИО (Фамилия Имя Отчество) одним сообщением:"
    )


@router.message(OnboardingStates.full_name)
async def process_name(message: Message, state: FSMContext, session):
    name = message.text.strip()
    if len(name.split()) < 3:
        await message.answer("Пожалуйста, введите полное ФИО (Фамилия Имя Отчество) одним сообщением:")
        return
    await state.update_data(full_name=name)
    await state.set_state(OnboardingStates.region)
    regions = await user_service.get_all_regions(session)
    await state.update_data(all_regions=regions)
    await message.answer(
        "Выберите ваш регион:",
        reply_markup=paginated_items_keyboard(regions, "onb_region"),
    )


@router.callback_query(OnboardingStates.region, F.data.startswith("onb_region_page:"))
async def process_region_page(callback: CallbackQuery, state: FSMContext):
    page = int(callback.data.split(":")[1])
    data = await state.get_data()
    regions = data["all_regions"]
    await callback.message.edit_reply_markup(
        reply_markup=paginated_items_keyboard(regions, "onb_region", page=page),
    )
    await callback.answer()


@router.callback_query(OnboardingStates.region, F.data.startswith("onb_region:"))
async def process_region_select(callback: CallbackQuery, state: FSMContext, session):
    region_id = int(callback.data.split(":")[1])
    await state.update_data(region_id=region_id)
    municipalities = await user_service.get_municipalities_by_region(session, region_id)
    if municipalities:
        await state.set_state(OnboardingStates.municipality)
        await state.update_data(all_municipalities=municipalities)
        await callback.message.edit_text(
            "Выберите муниципалитет:",
            reply_markup=paginated_items_keyboard(municipalities, "onb_muni"),
        )
    else:
        await state.set_state(OnboardingStates.school)
        schools = await user_service.get_schools_by_region(session, region_id)
        await state.update_data(all_schools=schools)
        await callback.message.edit_text(
            "Выберите вашу школу:",
            reply_markup=paginated_items_keyboard(schools, "onb_school", add_other=True),
        )
    await callback.answer()


@router.callback_query(OnboardingStates.municipality, F.data.startswith("onb_muni_page:"))
async def process_municipality_page(callback: CallbackQuery, state: FSMContext):
    page = int(callback.data.split(":")[1])
    data = await state.get_data()
    municipalities = data["all_municipalities"]
    await callback.message.edit_reply_markup(
        reply_markup=paginated_items_keyboard(municipalities, "onb_muni", page=page),
    )
    await callback.answer()


@router.callback_query(OnboardingStates.municipality, F.data.startswith("onb_muni:"))
async def process_municipality_select(callback: CallbackQuery, state: FSMContext, session):
    muni_idx = int(callback.data.split(":")[1])
    data = await state.get_data()
    region_id = data["region_id"]
    municipality = data["all_municipalities"][muni_idx]["name"]
    await state.set_state(OnboardingStates.school)
    schools = await user_service.get_schools_by_municipality(session, region_id, municipality)
    await state.update_data(all_schools=schools)
    await callback.message.edit_text(
        "Выберите вашу школу:",
        reply_markup=paginated_items_keyboard(schools, "onb_school", add_other=True),
    )
    await callback.answer()


@router.callback_query(OnboardingStates.school, F.data.startswith("onb_school_page:"))
async def process_school_page(callback: CallbackQuery, state: FSMContext):
    page = int(callback.data.split(":")[1])
    data = await state.get_data()
    schools = data["all_schools"]
    await callback.message.edit_reply_markup(
        reply_markup=paginated_items_keyboard(schools, "onb_school", page=page, add_other=True),
    )
    await callback.answer()


@router.callback_query(OnboardingStates.school, F.data == "onb_school:other")
async def process_school_other(callback: CallbackQuery, state: FSMContext):
    await state.set_state(OnboardingStates.school_other)
    await callback.message.edit_text("Введите название вашей школы:")
    await callback.answer()


@router.message(OnboardingStates.school_other, F.text)
async def process_school_other_text(message: Message, state: FSMContext, session):
    name = message.text.strip()
    if not name:
        await message.answer("Пожалуйста, введите название школы:")
        return
    data = await state.get_data()
    region_id = data["region_id"]
    school_id = await user_service.create_school(session, region_id, name)
    await state.update_data(school_id=school_id)
    await state.set_state(OnboardingStates.subjects)
    subjects = await user_service.get_all_subjects(session)
    await state.update_data(available_subjects=subjects, selected_subjects=[])
    await message.answer(
        "Какие предметы вы ведёте? Выберите и нажмите «Готово»:",
        reply_markup=subjects_toggle_keyboard(subjects, set()),
    )


@router.callback_query(OnboardingStates.school, F.data.startswith("onb_school:"))
async def process_school_select(callback: CallbackQuery, state: FSMContext, session):
    school_id = int(callback.data.split(":")[1])
    await state.update_data(school_id=school_id)
    await state.set_state(OnboardingStates.subjects)
    subjects = await user_service.get_all_subjects(session)
    await state.update_data(available_subjects=subjects, selected_subjects=[])
    await callback.message.edit_text(
        "Какие предметы вы ведёте? Выберите и нажмите «Готово»:",
        reply_markup=subjects_toggle_keyboard(subjects, set()),
    )
    await callback.answer()


@router.callback_query(OnboardingStates.subjects, F.data.startswith("onb_subj:"))
async def process_subject_toggle(callback: CallbackQuery, state: FSMContext):
    value = callback.data.split(":")[1]
    data = await state.get_data()
    selected = set(data.get("selected_subjects", []))
    subjects = data["available_subjects"]

    if value == "done":
        await state.update_data(subjects=list(selected))
        await state.set_state(OnboardingStates.phone)
        await callback.message.edit_text("Поделитесь номером телефона:")
        await callback.message.answer(
            "Нажмите кнопку ниже или введите номер вручную:",
            reply_markup=contact_keyboard(),
        )
        await callback.answer()
        return

    subj_id = int(value)
    if subj_id in selected:
        selected.discard(subj_id)
    else:
        selected.add(subj_id)
    await state.update_data(selected_subjects=list(selected))
    await callback.message.edit_reply_markup(
        reply_markup=subjects_toggle_keyboard(subjects, selected),
    )
    await callback.answer()


@router.message(OnboardingStates.phone, F.contact)
async def process_phone_contact(message: Message, state: FSMContext):
    await state.update_data(phone=message.contact.phone_number)
    # Remove contact keyboard
    await message.answer("Контакт получен.", reply_markup=ReplyKeyboardRemove())
    await state.set_state(OnboardingStates.email)
    await message.answer(
        "Введите email (или нажмите «Пропустить»):",
        reply_markup=skip_keyboard(),
    )


@router.message(OnboardingStates.phone, F.text)
async def process_phone_text(message: Message, state: FSMContext):
    phone = message.text.strip().replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    if not (phone.startswith("+7") and len(phone) == 12 and phone[1:].isdigit()):
        await message.answer("Введите номер в формате +7XXXXXXXXXX:")
        return
    await state.update_data(phone=phone)
    # Remove contact keyboard
    await message.answer("Номер получен.", reply_markup=ReplyKeyboardRemove())
    await state.set_state(OnboardingStates.email)
    await message.answer(
        "Введите email (или нажмите «Пропустить»):",
        reply_markup=skip_keyboard(),
    )


@router.message(OnboardingStates.email, F.text)
async def process_email(message: Message, state: FSMContext, session):
    await state.update_data(email=message.text.strip())
    await _finish_onboarding(message, state, session, telegram_id=message.from_user.id)


@router.callback_query(OnboardingStates.email, F.data == "onb_skip")
async def process_email_skip(callback: CallbackQuery, state: FSMContext, session):
    await _finish_onboarding(callback.message, state, session, telegram_id=callback.from_user.id)
    await callback.answer()


async def _finish_onboarding(message, state: FSMContext, session, telegram_id: int):
    data = await state.get_data()
    try:
        user_data = UserCreate(
            telegram_id=telegram_id,
            full_name=data["full_name"],
            phone=data["phone"],
            email=data.get("email"),
            region_id=data["region_id"],
            school_id=data["school_id"],
            subjects=data.get("subjects", []),
        )
        await user_service.create_user(session, user_data)
    except Exception:
        logger.exception("Failed to create user")
        await message.answer("Ошибка при регистрации. Попробуйте позже или начните заново /start")
        return
    await state.clear()
    await message.answer(
        "Регистрация завершена!\n\n"
        "Выберите способ поиска:",
        reply_markup=search_choice_keyboard(),
    )
