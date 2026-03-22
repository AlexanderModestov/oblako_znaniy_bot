import json
import logging

import gspread
from google.oauth2.service_account import Credentials
from openai import AsyncOpenAI
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import get_settings
from src.core.models import (
    Course,
    Lesson,
    LessonLink,
    Municipality,
    Region,
    School,
    Section,
    Subject,
    Topic,
)

logger = logging.getLogger(__name__)

BATCH_SIZE = 500


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _str(row: dict, key: str) -> str:
    """Get string value from row dict, stripped."""
    return str(row.get(key, "")).strip()


def _int_or_none(row: dict, key: str) -> int | None:
    """Parse int or return None."""
    val = _str(row, key)
    if not val:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def _bool_field(row: dict, key: str) -> bool:
    """Parse bool (true if value is '1', 'true', 'да', 'yes')."""
    val = _str(row, key).lower()
    return val in ("1", "true", "да", "yes")


# ---------------------------------------------------------------------------
# Google Sheets client
# ---------------------------------------------------------------------------

def _get_gspread_client() -> gspread.Client:
    settings = get_settings()
    creds_dict = json.loads(settings.google_service_account_json)
    creds = Credentials.from_service_account_info(
        creds_dict,
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
    )
    return gspread.authorize(creds)


# ---------------------------------------------------------------------------
# Fetch functions (read from Google Sheets)
# ---------------------------------------------------------------------------

def fetch_schools_from_sheets() -> list[dict]:
    """Open spreadsheet by schools_id, read ALL worksheets EXCEPT the first one."""
    settings = get_settings()
    client = _get_gspread_client()
    spreadsheet = client.open_by_key(settings.google_sheets_schools_id)
    worksheets = spreadsheet.worksheets()
    all_rows: list[dict] = []
    for ws in worksheets[1:]:  # skip first worksheet
        all_rows.extend(ws.get_all_records())
    return all_rows


def fetch_subjects_from_sheets() -> list[dict]:
    settings = get_settings()
    client = _get_gspread_client()
    spreadsheet = client.open_by_key(settings.google_sheets_lessons_id)
    return spreadsheet.worksheet("subject").get_all_records()


def fetch_courses_from_sheets() -> list[dict]:
    settings = get_settings()
    client = _get_gspread_client()
    spreadsheet = client.open_by_key(settings.google_sheets_lessons_id)
    return spreadsheet.worksheet("Курс").get_all_records()


def fetch_sections_from_sheets() -> list[dict]:
    settings = get_settings()
    client = _get_gspread_client()
    spreadsheet = client.open_by_key(settings.google_sheets_lessons_id)
    return spreadsheet.worksheet("Разделы").get_all_records()


def fetch_topics_from_sheets() -> list[dict]:
    settings = get_settings()
    client = _get_gspread_client()
    spreadsheet = client.open_by_key(settings.google_sheets_lessons_id)
    return spreadsheet.worksheet("Темы").get_all_records()


def fetch_lessons_from_sheets() -> list[dict]:
    settings = get_settings()
    client = _get_gspread_client()
    spreadsheet = client.open_by_key(settings.google_sheets_lessons_id)
    return spreadsheet.worksheet("Уроки").get_all_records()


def fetch_lesson_links_from_sheets() -> list[dict]:
    settings = get_settings()
    client = _get_gspread_client()
    spreadsheet = client.open_by_key(settings.google_sheets_lessons_id)
    return spreadsheet.worksheet("Ссылки").get_all_records()


# ---------------------------------------------------------------------------
# Embeddings
# ---------------------------------------------------------------------------

async def generate_embeddings(texts: list[str]) -> list[list[float]]:
    settings = get_settings()
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    embeddings = []
    batch_size = 2048
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        response = await client.embeddings.create(
            model="text-embedding-3-small",
            input=batch,
        )
        embeddings.extend([item.embedding for item in response.data])
    return embeddings


# ---------------------------------------------------------------------------
# Reload functions (upsert/insert to DB)
# ---------------------------------------------------------------------------

async def reload_schools_data(session: AsyncSession) -> dict:
    """Parse rows with columns: Регион, Наименование муниципалитета, Школа."""
    rows = fetch_schools_from_sheets()

    regions_set: set[str] = set()
    municipalities_dict: dict[tuple[str, str], None] = {}
    schools_list: list[dict] = []

    for row in rows:
        region = _str(row, "Регион")
        municipality = _str(row, "Наименование муниципалитета")
        school = _str(row, "Школа")
        if region:
            regions_set.add(region)
        if region and municipality:
            municipalities_dict[(region, municipality)] = None
        if region and school:
            schools_list.append({
                "region": region,
                "municipality": municipality or None,
                "school": school,
            })

    # Upsert regions
    if regions_set:
        stmt = pg_insert(Region).values([{"name": n} for n in regions_set])
        stmt = stmt.on_conflict_do_nothing(index_elements=["name"])
        await session.execute(stmt)
        await session.flush()

    result = await session.execute(select(Region))
    region_map = {r.name: r.id for r in result.scalars().all()}

    # Upsert municipalities
    muni_values = []
    for (region_name, muni_name) in municipalities_dict:
        region_id = region_map.get(region_name)
        if region_id and muni_name:
            muni_values.append({"region_id": region_id, "name": muni_name})

    for i in range(0, len(muni_values), BATCH_SIZE):
        batch = muni_values[i : i + BATCH_SIZE]
        stmt = pg_insert(Municipality).values(batch)
        stmt = stmt.on_conflict_do_nothing(constraint="uq_municipalities_region_id_name")
        await session.execute(stmt)
    await session.flush()

    # Build municipality map
    result = await session.execute(select(Municipality).join(Region))
    muni_map = {}
    for m in result.scalars().all():
        region_name = next((rn for rn, rid in region_map.items() if rid == m.region_id), None)
        if region_name:
            muni_map[(region_name, m.name)] = m.id

    # Upsert schools
    school_values = []
    for item in schools_list:
        muni_id = muni_map.get((item["region"], item["municipality"]))
        if muni_id:
            school_values.append({"municipality_id": muni_id, "name": item["school"]})

    for i in range(0, len(school_values), BATCH_SIZE):
        batch = school_values[i : i + BATCH_SIZE]
        stmt = pg_insert(School).values(batch)
        stmt = stmt.on_conflict_do_nothing(constraint="uq_schools_municipality_id_name")
        await session.execute(stmt)

    await session.commit()
    return {
        "regions": len(regions_set),
        "municipalities": len(muni_values),
        "schools": len(school_values),
    }


async def reload_subjects_data(session: AsyncSession) -> dict:
    """Parse 'subject' tab with columns: Name, Code. Upsert on name, update code."""
    rows = fetch_subjects_from_sheets()
    count = 0

    for row in rows:
        name = _str(row, "Name")
        code = _str(row, "Code") or None
        if not name:
            continue
        stmt = pg_insert(Subject).values(name=name, code=code)
        stmt = stmt.on_conflict_do_update(
            index_elements=["name"],
            set_={"code": stmt.excluded.code},
        )
        await session.execute(stmt)
        count += 1

    await session.commit()
    return {"subjects": count}


async def reload_courses_data(session: AsyncSession) -> dict:
    """Parse 'Курс' tab. Upsert on id."""
    rows = fetch_courses_from_sheets()
    count = 0

    for row in rows:
        course_id = _int_or_none(row, "ИД курса")
        if course_id is None:
            continue
        values = {
            "id": course_id,
            "name": _str(row, "Наименование"),
            "description": _str(row, "Описание") or None,
            "actual": _bool_field(row, "Актуальность"),
            "demo_link": _str(row, "Ссылка на демо") or None,
            "methodology_link": _str(row, "Ссылка на методичку") or None,
            "standard": _str(row, "Стандарты") or None,
            "skills": _str(row, "Навыки") or None,
            "deleted": _bool_field(row, "Удалено"),
            "status_msh": _str(row, "Статус МШ") or None,
        }
        stmt = pg_insert(Course).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["id"],
            set_={k: stmt.excluded[k] for k in values if k != "id"},
        )
        await session.execute(stmt)
        count += 1

    await session.commit()
    return {"courses": count}


async def reload_sections_data(session: AsyncSession) -> dict:
    """Parse 'Разделы' tab. Upsert on id."""
    rows = fetch_sections_from_sheets()
    count = 0

    for row in rows:
        section_id = _int_or_none(row, "ИД раздела")
        if section_id is None:
            continue
        values = {
            "id": section_id,
            "course_id": _int_or_none(row, "ИД курса"),
            "name": _str(row, "Наименование"),
            "description": _str(row, "Описание") or None,
            "actual": _bool_field(row, "Актуальность"),
            "demo_link": _str(row, "Ссылка на демо") or None,
            "methodology_link": _str(row, "Ссылка на методичку") or None,
            "standard": _str(row, "Стандарты") or None,
            "skills": _str(row, "Навыки") or None,
            "deleted": _bool_field(row, "Удалено"),
            "status_msh": _str(row, "Статус МШ") or None,
        }
        stmt = pg_insert(Section).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["id"],
            set_={k: stmt.excluded[k] for k in values if k != "id"},
        )
        await session.execute(stmt)
        count += 1

    await session.commit()
    return {"sections": count}


async def reload_topics_data(session: AsyncSession) -> dict:
    """Parse 'Темы' tab. Upsert on id. NOTE: No 'Стандарты' column."""
    rows = fetch_topics_from_sheets()
    count = 0

    for row in rows:
        topic_id = _int_or_none(row, "ИД темы")
        if topic_id is None:
            continue
        values = {
            "id": topic_id,
            "section_id": _int_or_none(row, "ИД раздела"),
            "name": _str(row, "Наименование"),
            "description": _str(row, "Описание") or None,
            "actual": _bool_field(row, "Актуальность"),
            "demo_link": _str(row, "Ссылка на демо") or None,
            "methodology_link": _str(row, "Ссылка на методичку") or None,
            "skills": _str(row, "Навыки") or None,
            "deleted": _bool_field(row, "Удалено"),
            "status_msh": _str(row, "Статус МШ") or None,
        }
        stmt = pg_insert(Topic).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["id"],
            set_={k: stmt.excluded[k] for k in values if k != "id"},
        )
        await session.execute(stmt)
        count += 1

    await session.commit()
    return {"topics": count}


async def reload_lessons_data(session: AsyncSession) -> dict:
    """Parse 'Уроки' tab. Full reload: delete all LessonLinks, delete all Lessons, batch insert."""
    logger.info("Fetching lessons from Google Sheets...")
    rows = fetch_lessons_from_sheets()

    # Build subject map
    result = await session.execute(select(Subject))
    subject_map = {s.name: s.id for s in result.scalars().all()}

    # Parse rows
    lessons = []
    errors: list[int] = []
    for i, row in enumerate(rows, start=2):
        lesson_id = _int_or_none(row, "ИД урока")
        subject_name = _str(row, "Предмет")
        grade = _int_or_none(row, "Класс")
        title = _str(row, "Урок")
        url = _str(row, "Ссылка УБ ЦОК")

        if not lesson_id or not subject_name or grade is None or not title:
            logger.warning("Row %d: missing required field(s)", i)
            errors.append(i)
            continue

        subject_id = subject_map.get(subject_name)
        if not subject_id:
            logger.warning("Row %d: unknown subject '%s'", i, subject_name)
            errors.append(i)
            continue

        lessons.append({
            "id": lesson_id,
            "subject_id": subject_id,
            "grade": grade,
            "title": title,
            "url": url or "",
            "description": _str(row, "Описание урока") or None,
            "course_id": _int_or_none(row, "Курс"),
            "section_id": _int_or_none(row, "Раздел"),
            "topic_id": _int_or_none(row, "Тема"),
        })

    logger.info("Parsed %d lessons, %d errors", len(lessons), len(errors))

    # Delete existing data (LessonLinks first due to FK)
    await session.execute(delete(LessonLink))
    await session.execute(delete(Lesson))

    # Generate embeddings from title + description
    texts = [
        " ".join(filter(None, [l["title"], l["description"]]))
        for l in lessons
    ]
    try:
        logger.info("Generating embeddings for %d lessons...", len(texts))
        embeddings = await generate_embeddings(texts)
    except Exception:
        logger.exception("Failed to generate embeddings")
        embeddings = [None] * len(lessons)

    # Batch insert
    for i in range(0, len(lessons), BATCH_SIZE):
        batch = lessons[i : i + BATCH_SIZE]
        batch_embeddings = embeddings[i : i + BATCH_SIZE]
        values = [
            {**lesson, "embedding": batch_embeddings[j]}
            for j, lesson in enumerate(batch)
        ]
        await session.execute(Lesson.__table__.insert(), values)
        logger.info(
            "Inserted lessons %d-%d of %d",
            i + 1, min(i + BATCH_SIZE, len(lessons)), len(lessons),
        )

    await session.commit()
    return {
        "loaded": len(lessons),
        "errors": len(errors),
        "error_rows": errors,
        "embeddings": embeddings[0] is not None if embeddings else False,
    }


async def reload_lesson_links_data(session: AsyncSession) -> dict:
    """Parse 'Ссылки' tab. Full reload: delete all LessonLinks, batch insert."""
    rows = fetch_lesson_links_from_sheets()

    await session.execute(delete(LessonLink))

    # Handle possible double space in header "URL  в УБ ЦОК"
    link_values = []
    for row in rows:
        lesson_id = _int_or_none(row, "ИД урока")
        if not lesson_id:
            continue
        # Try both single and double space variants
        url = _str(row, "URL  в УБ ЦОК") or _str(row, "URL в УБ ЦОК")
        if not url:
            continue
        link_values.append({"lesson_id": lesson_id, "url": url})

    for i in range(0, len(link_values), BATCH_SIZE):
        batch = link_values[i : i + BATCH_SIZE]
        await session.execute(LessonLink.__table__.insert(), batch)

    await session.commit()
    return {"links": len(link_values)}
