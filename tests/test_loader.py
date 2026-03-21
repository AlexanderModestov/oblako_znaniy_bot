from src.core.services.loader import (
    parse_lessons_rows,
    parse_regions_schools_rows,
    validate_lesson_row,
)


def test_validate_lesson_row_valid():
    row = {
        "Предмет": "Физика",
        "Класс": "11",
        "Курс": "Облако знаний. Подготовка к ЕГЭ. Физика, 11 класс",
        "Раздел": "Вступительное тестирование",
        "Тема": "Вступительное тестирование",
        "Урок": "КИМ ЕГЭ по физике. Тренировочный вариант 1",
        "Ссылка УБ ЦОК": "https://www.gosuslugi.ru/edu-content/lesson/2873",
    }
    result = validate_lesson_row(row, row_num=2)
    assert result is not None
    assert result["subject"] == "Физика"
    assert result["grade"] == 11
    assert result["url"] == "https://www.gosuslugi.ru/edu-content/lesson/2873"


def test_validate_lesson_row_missing_url():
    row = {
        "Предмет": "Математика",
        "Класс": "5",
        "Раздел": "",
        "Тема": "",
        "Урок": "Тест",
        "Курс": "Теория",
        "Ссылка УБ ЦОК": "",
    }
    result = validate_lesson_row(row, row_num=2)
    assert result is None


def test_validate_lesson_row_missing_subject():
    row = {
        "Предмет": "",
        "Класс": "5",
        "Раздел": "",
        "Тема": "",
        "Урок": "Тест",
        "Курс": "Теория",
        "Ссылка УБ ЦОК": "https://gosuslugi.ru/123",
    }
    result = validate_lesson_row(row, row_num=2)
    assert result is None


def test_validate_lesson_row_invalid_grade():
    row = {
        "Предмет": "Математика",
        "Класс": "abc",
        "Раздел": "",
        "Тема": "",
        "Урок": "Тест",
        "Курс": "Теория",
        "Ссылка УБ ЦОК": "https://gosuslugi.ru/123",
    }
    result = validate_lesson_row(row, row_num=2)
    assert result is None


def test_validate_lesson_row_empty_optional_fields():
    row = {
        "Предмет": "Биология",
        "Класс": "9",
        "Раздел": "",
        "Тема": "",
        "Урок": "Фотосинтез",
        "Курс": "",
        "Ссылка УБ ЦОК": "https://gosuslugi.ru/456",
    }
    result = validate_lesson_row(row, row_num=3)
    assert result is not None
    assert result["section"] is None
    assert result["topic"] is None
    assert result["lesson_type"] is None


def test_parse_lessons_rows():
    rows = [
        {
            "Предмет": "Физика",
            "Класс": "11",
            "Раздел": "Механика",
            "Тема": "Кинематика",
            "Урок": "Равномерное движение",
            "Курс": "Базовый курс",
            "Ссылка УБ ЦОК": "https://gosuslugi.ru/1",
        },
        {
            "Предмет": "",
            "Класс": "",
            "Раздел": "",
            "Тема": "",
            "Урок": "",
            "Курс": "",
            "Ссылка УБ ЦОК": "",
        },
    ]
    lessons, errors = parse_lessons_rows(rows)
    assert len(lessons) == 1
    assert len(errors) == 1


def test_parse_regions_schools_rows():
    rows = [
        {"Регион": "Москва", "Школа": "Школа №1"},
        {"Регион": "Москва", "Школа": "Школа №2"},
        {"Регион": "Санкт-Петербург", "Школа": "Гимназия №1"},
    ]
    regions, schools = parse_regions_schools_rows(rows)
    assert len(regions) == 2
    assert "Москва" in regions
    assert len(schools) == 3


def test_parse_regions_schools_rows_empty_values():
    rows = [
        {"Регион": "Москва", "Школа": "Школа №1"},
        {"Регион": "", "Школа": "Школа №2"},
        {"Регион": "Москва", "Школа": ""},
    ]
    regions, schools = parse_regions_schools_rows(rows)
    assert len(regions) == 1
    assert len(schools) == 1
