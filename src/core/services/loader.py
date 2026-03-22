import json
import logging

import gspread
from google.oauth2.service_account import Credentials
from openai import AsyncOpenAI
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import get_settings
from src.core.models import Lesson, Municipality, Region, School, Subject

logger = logging.getLogger(__name__)

REQUIRED_LESSON_FIELDS = ["Предмет", "Класс", "Урок", "Ссылка УБ ЦОК"]


def validate_lesson_row(row: dict, row_num: int) -> dict | None:
    for field in REQUIRED_LESSON_FIELDS:
        value = str(row.get(field, "")).strip()
        if not value:
            logger.warning("Row %d: missing required field '%s'", row_num, field)
            return None
    try:
        grade = int(str(row["Класс"]).strip())
    except ValueError:
        logger.warning("Row %d: invalid grade '%s'", row_num, row["Класс"])
        return None
    return {
        "subject": str(row["Предмет"]).strip(),
        "grade": grade,
        "section": str(row.get("Раздел", "")).strip() or None,
        "topic": str(row.get("Тема", "")).strip() or None,
        "title": str(row["Урок"]).strip(),
        "lesson_type": str(row.get("Курс", "")).strip() or None,
        "url": str(row["Ссылка УБ ЦОК"]).strip(),
    }


def parse_lessons_rows(rows: list[dict]) -> tuple[list[dict], list[int]]:
    lessons = []
    errors = []
    for i, row in enumerate(rows, start=2):
        parsed = validate_lesson_row(row, row_num=i)
        if parsed:
            lessons.append(parsed)
        else:
            errors.append(i)
    return lessons, errors


def parse_regions_schools_rows(rows: list[dict]) -> tuple[set[str], dict[str, set[str]], list[dict]]:
    regions = set()
    municipalities = {}  # {(region, municipality_name): set()}
    schools = []
    for row in rows:
        region = str(row.get("Регион", "")).strip()
        municipality = str(row.get("Наименование муниципалитета", "")).strip()
        school = str(row.get("Школа", "")).strip()
        if region:
            regions.add(region)
        if region and municipality:
            municipalities[(region, municipality)] = None
        if region and school:
            schools.append({
                "region": region,
                "municipality": municipality or None,
                "school": school,
            })
    return regions, municipalities, schools


def _get_gspread_client() -> gspread.Client:
    settings = get_settings()
    creds_dict = json.loads(settings.google_service_account_json)
    creds = Credentials.from_service_account_info(
        creds_dict,
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
    )
    return gspread.authorize(creds)


EXPECTED_HEADERS = [
    "ИД урока", "Предмет", "Класс", "Курс", "Раздел", "Тема", "Урок", "Ссылка УБ ЦОК",
]


def fetch_lessons_from_sheets() -> list[dict]:
    settings = get_settings()
    client = _get_gspread_client()
    sheet = client.open_by_key(settings.google_sheets_lessons_id).sheet1
    return sheet.get_all_records(expected_headers=EXPECTED_HEADERS)


def fetch_schools_from_sheets() -> list[dict]:
    settings = get_settings()
    client = _get_gspread_client()
    sheet = client.open_by_key(settings.google_sheets_schools_id).sheet1
    return sheet.get_all_records()


def fetch_subjects_from_sheets() -> list[dict]:
    settings = get_settings()
    client = _get_gspread_client()
    spreadsheet = client.open_by_key(settings.google_sheets_lessons_id)
    sheet = spreadsheet.worksheet("subjects")
    return sheet.get_all_records()


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


async def reload_subjects_data(session: AsyncSession) -> dict:
    rows = fetch_subjects_from_sheets()
    subject_names = []
    for row in rows:
        name = str(row.get("Name", "")).strip()
        if name:
            subject_names.append(name)

    if subject_names:
        stmt = pg_insert(Subject).values([{"name": n} for n in subject_names])
        stmt = stmt.on_conflict_do_nothing(index_elements=["name"])
        await session.execute(stmt)
        await session.commit()

    return {"subjects": len(subject_names)}


async def reload_schools_data(session: AsyncSession) -> dict:
    rows = fetch_schools_from_sheets()
    regions_set, municipalities_dict, schools_list = parse_regions_schools_rows(rows)

    # Batch upsert regions
    if regions_set:
        stmt = pg_insert(Region).values([{"name": n} for n in regions_set])
        stmt = stmt.on_conflict_do_nothing(index_elements=["name"])
        await session.execute(stmt)
        await session.flush()

    result = await session.execute(select(Region))
    region_map = {r.name: r.id for r in result.scalars().all()}

    # Batch upsert municipalities
    muni_values = []
    for (region_name, muni_name) in municipalities_dict:
        region_id = region_map.get(region_name)
        if region_id and muni_name:
            muni_values.append({"region_id": region_id, "name": muni_name})

    for i in range(0, len(muni_values), 500):
        batch = muni_values[i : i + 500]
        stmt = pg_insert(Municipality).values(batch)
        stmt = stmt.on_conflict_do_nothing(constraint="uq_municipalities_region_id_name")
        await session.execute(stmt)
    await session.flush()

    # Build municipality map: (region_name, muni_name) -> muni_id
    result = await session.execute(select(Municipality).join(Region))
    muni_map = {}
    for m in result.scalars().all():
        region_name = next((rn for rn, rid in region_map.items() if rid == m.region_id), None)
        if region_name:
            muni_map[(region_name, m.name)] = m.id

    # Batch upsert schools in chunks of 500
    school_values = []
    for item in schools_list:
        muni_id = muni_map.get((item["region"], item["municipality"]))
        if muni_id:
            school_values.append({"municipality_id": muni_id, "name": item["school"]})

    for i in range(0, len(school_values), 500):
        batch = school_values[i : i + 500]
        stmt = pg_insert(School).values(batch)
        stmt = stmt.on_conflict_do_nothing(constraint="uq_schools_municipality_id_name")
        await session.execute(stmt)

    await session.commit()
    return {"regions": len(regions_set), "municipalities": len(muni_values), "schools": len(school_values)}


async def reload_lessons_data(session: AsyncSession) -> dict:
    logger.info("Fetching lessons from Google Sheets...")
    rows = fetch_lessons_from_sheets()
    lessons, errors = parse_lessons_rows(rows)
    logger.info("Parsed %d lessons, %d errors", len(lessons), len(errors))

    # Batch upsert subjects
    subject_names = {lesson["subject"] for lesson in lessons}
    if subject_names:
        stmt = pg_insert(Subject).values([{"name": n} for n in subject_names])
        stmt = stmt.on_conflict_do_nothing(index_elements=["name"])
        await session.execute(stmt)
        await session.flush()

    result = await session.execute(select(Subject))
    subject_map = {s.name: s.id for s in result.scalars().all()}

    await session.execute(delete(Lesson))

    # Generate embeddings
    texts = [
        " ".join(filter(None, [l["title"], l["section"], l["topic"]]))
        for l in lessons
    ]
    try:
        logger.info("Generating embeddings for %d lessons...", len(texts))
        embeddings = await generate_embeddings(texts)
    except Exception:
        logger.exception("Failed to generate embeddings")
        embeddings = [None] * len(lessons)

    # Batch insert lessons in chunks of 500
    for i in range(0, len(lessons), 500):
        batch = lessons[i : i + 500]
        batch_embeddings = embeddings[i : i + 500]
        values = [
            {
                "subject_id": subject_map[lesson["subject"]],
                "grade": lesson["grade"],
                "section": lesson["section"],
                "topic": lesson["topic"],
                "title": lesson["title"],
                "lesson_type": lesson["lesson_type"],
                "url": lesson["url"],
                "embedding": batch_embeddings[j],
            }
            for j, lesson in enumerate(batch)
        ]
        await session.execute(Lesson.__table__.insert(), values)
        logger.info("Inserted lessons %d-%d of %d", i + 1, min(i + 500, len(lessons)), len(lessons))

    await session.commit()
    return {
        "loaded": len(lessons),
        "errors": len(errors),
        "error_rows": errors,
        "embeddings": embeddings[0] is not None if embeddings else False,
    }
