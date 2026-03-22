# Database Redesign

## Overview

Restructure the database from a flat lesson model to a normalized hierarchy,
add municipality level to the school hierarchy, and load data from multiple
Google Sheets tabs in the correct order.

## Data Sources

### Spreadsheet 1: Schools

All tabs except the first. Columns: Регион, municipality, Наименование муниципалитета, Школа.

### Spreadsheet 2: Content

| Tab | Columns |
|-----|---------|
| subject | Id, Name, Code |
| Курс | ИД курса, Наименование, Описание, Актуальность, Ссылка на демо, Ссылка на методичку, Стандарты, Навыки, Удалено, Статус МШ |
| Разделы | ИД раздела, ИД курса, Наименование, Описание, Актуальность, Ссылка на демо, Ссылка на методичку, Стандарты, Навыки, Удалено, Статус МШ |
| Темы | ИД темы, ИД раздела, Наименование, Описание, Актуальность, Ссылка на демо, Ссылка на методичку, Навыки, Удалено, Статус МШ |
| Уроки | ИД урока, Предмет, Класс, Курс, Раздел, Тема, Урок, Ссылка УБ ЦОК, Описание урока |
| Ссылки | ИД урока, URL в УБ ЦОК |

## Database Schema

### School Hierarchy

```
regions
  id (PK)
  name (unique)

municipalities
  id (PK)
  region_id (FK → regions)
  name
  UNIQUE(region_id, name)

schools
  id (PK)
  municipality_id (FK → municipalities)
  name
  UNIQUE(municipality_id, name)
```

### Content Hierarchy

```
subjects
  id (PK)
  name (unique)
  code

courses
  id (PK)
  name
  description
  actual (bool)
  demo_link
  methodology_link
  standard
  skills
  deleted (bool)
  status_msh

sections
  id (PK)
  course_id (FK → courses)
  name
  description
  actual (bool)
  demo_link
  methodology_link
  standard
  skills
  deleted (bool)
  status_msh

topics
  id (PK)
  section_id (FK → sections)
  name
  description
  actual (bool)
  demo_link
  methodology_link
  skills
  deleted (bool)
  status_msh

lessons
  id (PK)
  subject_id (FK → subjects)
  grade (smallint)
  course_id (FK → courses)
  section_id (FK → sections)
  topic_id (FK → topics)
  title
  url
  description
  search_vector (tsvector)
  embedding (vector 1536)
  created_at

lesson_links
  id (PK)
  lesson_id (FK → lessons)
  url
```

### Users (unchanged)

```
users
  id (PK)
  telegram_id (bigint, unique)
  full_name
  phone
  email
  region_id (FK → regions)
  school_id (FK → schools)
  subjects (array of smallint)
  created_at
  updated_at
```

## Data Loading Order

FK dependencies dictate this strict order:

### Spreadsheet 1 (schools):
1. Regions → upsert
2. Municipalities → upsert
3. Schools → upsert

### Spreadsheet 2 (content):
4. Subjects (tab "subject") → upsert
5. Courses (tab "Курс") → upsert
6. Sections (tab "Разделы") → upsert
7. Topics (tab "Темы") → upsert
8. Lessons (tab "Уроки") → delete all + batch insert
9. Lesson Links (tab "Ссылки") → delete all + batch insert
10. Embeddings → generate for lessons

### Update Strategy
- Reference data (regions, municipalities, schools, subjects, courses, sections, topics): **upsert** (on conflict do update)
- Lessons and links: **full reload** (delete + insert)

## Key Decisions

- `lessons.url` kept alongside `lesson_links` table (duplication, will normalize later)
- Users table unchanged; no FK to municipalities (derived via school → municipality → region)
- `subjects.subjects` in users remains as `ARRAY(SmallInteger)` without FK constraint
- "Удалено" and "Статус МШ" fields stored in DB (not filtered on load)
