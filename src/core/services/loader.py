import json
import logging

import gspread
from google.oauth2.service_account import Credentials
from openai import AsyncOpenAI
from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import get_settings
from src.core.models import (
    Course,
    Lesson,
    LessonLink,
    Region,
    School,
    Section,
    Subject,
    Topic,
    User,
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

SCHOOL_HEADERS = ["Регион", "муниципалитет", "школа", "ИНН"]


def _parse_sheet_with_headers(ws, headers: list[str]) -> list[dict]:
    """Read raw values and map columns by matching actual headers to expected ones."""
    all_values = ws.get_all_values()
    if not all_values:
        return []
    # Read actual headers from first row and find column indices
    actual_headers = [h.strip() for h in all_values[0]]
    col_map = {}  # header_name -> column_index
    for header in headers:
        if header in actual_headers:
            col_map[header] = actual_headers.index(header)
    unmapped = [h for h in headers if h not in col_map]
    if unmapped:
        logger.warning(
            "Sheet '%s': unmapped headers %s. Actual headers: %s",
            ws.title, unmapped, actual_headers[:15],
        )
    # Use first mapped column as row validity check (filters phantom .xlsx rows)
    first_col_idx = col_map.get(headers[0])
    raw_count = len(all_values) - 1
    rows = []
    for row_values in all_values[1:]:
        # Skip rows where the primary column (first header) is empty
        if first_col_idx is not None and (
            first_col_idx >= len(row_values) or not row_values[first_col_idx].strip()
        ):
            continue
        if not any(v.strip() for v in row_values):
            continue
        row = {}
        for header in headers:
            idx = col_map.get(header)
            row[header] = row_values[idx].strip() if idx is not None and idx < len(row_values) else ""
        rows.append(row)
    if raw_count != len(rows):
        logger.info("Sheet '%s': %d raw rows, %d after filtering phantom rows", ws.title, raw_count, len(rows))
    return rows


def fetch_schools_from_sheets() -> list[dict]:
    """Open spreadsheet by schools_id, read first worksheet."""
    settings = get_settings()
    client = _get_gspread_client()
    spreadsheet = client.open_by_key(settings.google_sheets_schools_id)
    ws = spreadsheet.worksheets()[0]
    return _parse_sheet_with_headers(ws, SCHOOL_HEADERS)


SUBJECT_HEADERS = ["Id", "Name"]
COURSE_HEADERS = ["ИД курса", "Наименование", "Описание", "Актуальность", "Ссылка на демо", "Ссылка на методичку", "Стандарты", "Навыки", "Удалено", "Статус МШ"]
SECTION_HEADERS = ["ИД раздела", "ИД курса", "Наименование", "Описание", "Актуальность", "Ссылка на демо", "Ссылка на методичку", "Стандарты", "Навыки", "Удалено", "Статус МШ"]
TOPIC_HEADERS = ["ИД темы", "ИД раздела", "Наименование", "Описание", "Актуальность", "Ссылка на демо", "Ссылка на методичку", "Навыки", "Удалено", "Статус МШ"]
LESSON_HEADERS = ["ИД урока", "Предмет", "Класс", "Курс", "Раздел", "Тема", "Урок", "Ссылка УБ ЦОК", "Описание урока"]
LINK_HEADERS = ["ИД урока", "URL  в УБ ЦОК"]


def fetch_all_content_from_sheets() -> dict[str, list[dict]]:
    """Open lessons spreadsheet once, read all tabs, return dict of tab_name -> rows."""
    settings = get_settings()
    client = _get_gspread_client()
    spreadsheet = client.open_by_key(settings.google_sheets_lessons_id)
    result = {
        "subjects": _parse_sheet_with_headers(spreadsheet.worksheet("subjects"), SUBJECT_HEADERS),
        "courses": _parse_sheet_with_headers(spreadsheet.worksheet("Курсы"), COURSE_HEADERS),
        "sections": _parse_sheet_with_headers(spreadsheet.worksheet("Разделы"), SECTION_HEADERS),
        "topics": _parse_sheet_with_headers(spreadsheet.worksheet("Темы"), TOPIC_HEADERS),
        "lessons": _parse_sheet_with_headers(spreadsheet.worksheet("Уроки"), LESSON_HEADERS),
        "links": _parse_sheet_with_headers(spreadsheet.worksheet("Ссылки"), LINK_HEADERS),
    }
    for name, rows in result.items():
        logger.info("Fetched %d rows from '%s'", len(rows), name)
    return result


# ---------------------------------------------------------------------------
# Embeddings
# ---------------------------------------------------------------------------

async def generate_embeddings(texts: list[str]) -> list[list[float]]:
    settings = get_settings()
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    embeddings = []
    batch_size = 500
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
    """Full reload: detach users, delete old schools/regions, insert fresh data."""
    rows = fetch_schools_from_sheets()

    regions_set: set[str] = set()
    schools_list: list[dict] = []

    for row in rows:
        region = _str(row, "Регион")
        municipality = _str(row, "муниципалитет") or None
        school = _str(row, "школа")
        inn = _str(row, "ИНН") or None
        if region:
            regions_set.add(region)
        if region and school:
            schools_list.append({
                "region": region,
                "municipality": municipality,
                "school": school,
                "inn": inn,
            })

    # Detach users from schools/regions, then wipe schools and regions
    detached = (await session.execute(
        update(User).where(User.school_id.is_not(None)).values(school_id=None, region_id=None)
    )).rowcount
    await session.execute(delete(School))
    await session.execute(delete(Region))
    await session.flush()
    logger.info("Detached %d users from schools/regions", detached)

    # Insert regions
    if regions_set:
        await session.execute(
            Region.__table__.insert(),
            [{"name": n} for n in sorted(regions_set)],
        )
        await session.flush()

    result = await session.execute(select(Region))
    region_map = {r.name: r.id for r in result.scalars().all()}

    # Insert schools (deduplicate by region_id + name, last row wins)
    school_map: dict[tuple, dict] = {}
    for item in schools_list:
        region_id = region_map.get(item["region"])
        if region_id:
            key = (region_id, item["school"])
            school_map[key] = {
                "region_id": region_id,
                "municipality": item["municipality"],
                "name": item["school"],
                "inn": item["inn"],
            }
    school_values = list(school_map.values())

    for i in range(0, len(school_values), BATCH_SIZE):
        batch = school_values[i : i + BATCH_SIZE]
        await session.execute(School.__table__.insert(), batch)

    await session.commit()
    return {
        "regions": len(regions_set),
        "schools": len(school_values),
        "users_detached": detached,
    }


async def reload_subjects_data(session: AsyncSession, rows: list[dict]) -> dict:
    """Parse 'subjects' tab with columns: Id, Name. Upsert on name."""
    values = []
    for row in rows:
        name = _str(row, "Name")
        if not name:
            continue
        values.append({"name": name})

    for i in range(0, len(values), BATCH_SIZE):
        batch = values[i : i + BATCH_SIZE]
        stmt = pg_insert(Subject).values(batch)
        stmt = stmt.on_conflict_do_nothing(index_elements=["name"])
        await session.execute(stmt)

    await session.commit()
    return {"subjects": len(values)}


async def reload_courses_data(session: AsyncSession, rows: list[dict]) -> dict:
    """Parse 'Курс' tab. Upsert on id."""
    values = []
    for row in rows:
        course_id = _int_or_none(row, "ИД курса")
        name = _str(row, "Наименование")
        if course_id is None or not name:
            continue
        values.append({
            "id": course_id,
            "name": name,
            "description": _str(row, "Описание") or None,
            "actual": _bool_field(row, "Актуальность"),
            "demo_link": _str(row, "Ссылка на демо") or None,
            "methodology_link": _str(row, "Ссылка на методичку") or None,
            "standard": _str(row, "Стандарты") or None,
            "skills": _str(row, "Навыки") or None,
            "deleted": _bool_field(row, "Удалено"),
            "status_msh": _str(row, "Статус МШ") or None,
        })

    # Deduplicate by id (last wins)
    deduped = {v["id"]: v for v in values}
    values = list(deduped.values())

    update_fields = [
        "name", "description", "actual", "demo_link", "methodology_link",
        "standard", "skills", "deleted", "status_msh",
    ]
    for i in range(0, len(values), BATCH_SIZE):
        batch = values[i : i + BATCH_SIZE]
        stmt = pg_insert(Course).values(batch)
        stmt = stmt.on_conflict_do_update(
            index_elements=["id"],
            set_={k: stmt.excluded[k] for k in update_fields},
        )
        await session.execute(stmt)

    await session.commit()
    return {"courses": len(values)}


async def reload_sections_data(session: AsyncSession, rows: list[dict]) -> dict:
    """Parse 'Разделы' tab. Upsert on id."""
    values = []
    skipped = 0
    for row in rows:
        section_id = _str(row, "ИД раздела")
        course_id = _int_or_none(row, "ИД курса")
        name = _str(row, "Наименование")
        if not section_id or course_id is None or not name:
            skipped += 1
            continue
        values.append({
            "id": section_id,  # string like "s12581437"
            "course_id": course_id,
            "name": name,
            "description": _str(row, "Описание") or None,
            "actual": _bool_field(row, "Актуальность"),
            "demo_link": _str(row, "Ссылка на демо") or None,
            "methodology_link": _str(row, "Ссылка на методичку") or None,
            "standard": _str(row, "Стандарты") or None,
            "skills": _str(row, "Навыки") or None,
            "deleted": _bool_field(row, "Удалено"),
            "status_msh": _str(row, "Статус МШ") or None,
        })

    # Deduplicate by id (last wins) — required for ON CONFLICT DO UPDATE
    deduped = {v["id"]: v for v in values}
    values = list(deduped.values())

    update_fields = [
        "course_id", "name", "description", "actual", "demo_link",
        "methodology_link", "standard", "skills", "deleted", "status_msh",
    ]
    for i in range(0, len(values), BATCH_SIZE):
        batch = values[i : i + BATCH_SIZE]
        stmt = pg_insert(Section).values(batch)
        stmt = stmt.on_conflict_do_update(
            index_elements=["id"],
            set_={k: stmt.excluded[k] for k in update_fields},
        )
        await session.execute(stmt)

    await session.commit()
    logger.info("Sections: %d loaded, %d skipped, %d deduped", len(values), skipped, len(deduped) - len(values) if len(deduped) != len(values) else 0)
    return {"sections": len(values)}


async def reload_topics_data(session: AsyncSession, rows: list[dict]) -> dict:
    """Parse 'Темы' tab. Upsert on id. NOTE: No 'Стандарты' column."""
    # Get existing section IDs to skip orphaned topics
    result = await session.execute(select(Section.id))
    existing_section_ids = {row[0] for row in result.all()}

    values = []
    skipped = 0
    for row in rows:
        topic_id = _str(row, "ИД темы")
        section_id = _str(row, "ИД раздела")
        name = _str(row, "Наименование")
        if not topic_id or not section_id or not name:
            skipped += 1
            continue
        if section_id not in existing_section_ids:
            skipped += 1
            continue
        values.append({
            "id": topic_id,  # string like "t12581437"
            "section_id": section_id,  # string like "s12581437"
            "name": name,
            "description": _str(row, "Описание") or None,
            "actual": _bool_field(row, "Актуальность"),
            "demo_link": _str(row, "Ссылка на демо") or None,
            "methodology_link": _str(row, "Ссылка на методичку") or None,
            "skills": _str(row, "Навыки") or None,
            "deleted": _bool_field(row, "Удалено"),
            "status_msh": _str(row, "Статус МШ") or None,
        })

    # Deduplicate by id (last wins)
    deduped = {v["id"]: v for v in values}
    values = list(deduped.values())
    if skipped:
        logger.warning("Topics: skipped %d rows (missing fields or orphaned section_id)", skipped)

    update_fields = [
        "section_id", "name", "description", "actual", "demo_link",
        "methodology_link", "skills", "deleted", "status_msh",
    ]
    for i in range(0, len(values), BATCH_SIZE):
        batch = values[i : i + BATCH_SIZE]
        stmt = pg_insert(Topic).values(batch)
        stmt = stmt.on_conflict_do_update(
            index_elements=["id"],
            set_={k: stmt.excluded[k] for k in update_fields},
        )
        await session.execute(stmt)

    await session.commit()
    return {"topics": len(values)}


async def reload_lessons_data(session: AsyncSession, rows: list[dict]) -> dict:
    """Parse 'Уроки' tab. Full reload: delete all LessonLinks, delete all Lessons, batch insert."""
    logger.info("Processing %d lesson rows...", len(rows))

    # Build lookup map for subject FK validation
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

        if not lesson_id or not subject_name or grade is None or not title or not url:
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
            "url": url,
            "description": _str(row, "Описание урока") or None,
            "course": _str(row, "Курс") or None,
            "section": _str(row, "Раздел") or None,
            "topic": _str(row, "Тема") or None,
        })

    # Deduplicate by id (last wins)
    before_dedup = len(lessons)
    lessons = list({l["id"]: l for l in lessons}.values())

    logger.info("Parsed %d lessons, %d errors, %d dupes removed", len(lessons), len(errors), before_dedup - len(lessons))

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


async def reload_lesson_links_data(session: AsyncSession, rows: list[dict]) -> dict:
    """Parse 'Ссылки' tab. Full reload: delete all LessonLinks, batch insert."""

    await session.execute(delete(LessonLink))

    # Get existing lesson IDs to skip orphaned links
    result = await session.execute(select(Lesson.id))
    existing_lesson_ids = {row[0] for row in result.all()}

    link_values = []
    skipped = 0
    for row in rows:
        lesson_id = _int_or_none(row, "ИД урока")
        if not lesson_id:
            continue
        url = _str(row, "URL  в УБ ЦОК")
        if not url:
            continue
        if lesson_id not in existing_lesson_ids:
            skipped += 1
            continue
        link_values.append({"lesson_id": lesson_id, "url": url})

    for i in range(0, len(link_values), BATCH_SIZE):
        batch = link_values[i : i + BATCH_SIZE]
        await session.execute(LessonLink.__table__.insert(), batch)

    await session.commit()
    if skipped:
        logger.warning("Skipped %d lesson links with non-existent lesson_id", skipped)
    return {"links": len(link_values)}
