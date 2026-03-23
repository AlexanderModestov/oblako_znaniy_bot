from src.core.schemas import LessonResult, SearchResult


def format_lesson_param(lesson: LessonResult) -> str:
    return (
        f"\U0001f4da {lesson.title}\n"
        f"\u2192 {lesson.url}"
    )


def format_lesson_text(lesson: LessonResult, index: int) -> str:
    semantic_mark = "\U0001f916 " if lesson.is_semantic else ""
    parts = [p for p in [lesson.subject, lesson.section, lesson.topic] if p]
    context = " | ".join(parts)
    return (
        f"{index}. {semantic_mark}{context}\n"
        f"   \U0001f4da {lesson.title}\n"
        f"   \u2192 {lesson.url}"
    )


def format_param_results(lessons: list[LessonResult]) -> str:
    if not lessons:
        return "Ничего не найдено. Попробуйте изменить параметры поиска."
    return "\n\n".join(format_lesson_param(l) for l in lessons)


def format_topic_lessons(lessons: list[LessonResult]) -> str:
    if not lessons:
        return "В данной теме пока нет уроков."
    first = lessons[0]
    parts = [p for p in [first.subject, first.section, first.topic] if p]
    header = " | ".join(parts)
    items = "\n\n".join(
        f"{i}. \U0001f4da {l.title}\n   \u2192 {l.url}"
        for i, l in enumerate(lessons, 1)
    )
    return f"\U0001f4cb {header}\n\nУроки ({len(lessons)}):\n\n{items}"


def format_text_results(result: SearchResult) -> str:
    if not result.lessons:
        return (
            f'\U0001f50e По запросу \u00ab{result.query}\u00bb ничего не найдено.\n'
            "Попробуйте другие ключевые слова."
        )
    header = f'\U0001f50e По запросу \u00ab{result.query}\u00bb найдено {result.total} результатов:\n\n'
    start_index = (result.page - 1) * result.per_page + 1
    items = "\n\n".join(
        format_lesson_text(l, start_index + i)
        for i, l in enumerate(result.lessons)
    )
    return header + items
