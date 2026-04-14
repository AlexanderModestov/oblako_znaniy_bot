from src.core.schemas import LessonResult, SearchResult

_IN_DEVELOPMENT = "\u23f3 На данный момент урок находится в разработке, добавим его чуть позже"


def _url_line(url: str, indent: str = "") -> str:
    if url == "N/A":
        return f"{indent}{_IN_DEVELOPMENT}"
    return f"{indent}\u2192 {url}"


def format_lesson_text(lesson: LessonResult, index: int) -> str:
    semantic_mark = "\U0001f916 " if lesson.is_semantic else ""
    grade_str = f"{lesson.grade} класс" if lesson.grade else None
    parts = [p for p in [lesson.subject, grade_str, lesson.section, lesson.topic] if p]
    context = " | ".join(parts)
    snippet_line = f"\n   \U0001f4ac {lesson.snippet}" if lesson.snippet else ""
    return (
        f"{index}. {semantic_mark}{context}\n"
        f"   \U0001f4da {lesson.title}"
        f"{snippet_line}\n"
        f"{_url_line(lesson.url, '   ')}"
    )


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


def format_empty_level_2_results(query: str) -> str:
    """Shown when the extended (level 2) search returned no lessons at all."""
    return (
        f'\U0001f50e Расширенный поиск по запросу \u00ab{query}\u00bb не дал результатов.\n\n'
        "Попробуйте сформулировать запрос иначе."
    )
