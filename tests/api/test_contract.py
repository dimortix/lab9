# -*- coding: utf-8 -*-
"""
Контрактные тесты REST API.

Здесь проверяется не поведение отдельных сценариев, а **контракт** —
договорённость между сервисом и его клиентами:

* обязательные поля и их типы;
* отсутствие лишних полей (``additionalProperties: false``);
* вложенность структур (address → geo — три уровня);
* согласованность данных между эндпоинтами (запись в коллекции и по id);
* форматы значений (email, координаты, домен сайта);
* единообразие заголовков.

Нарушение любого из этих тестов означает, что клиентский код сломается,
даже если «функционально» сервис продолжает работать.

Идентификаторы тестов (TC-xx) совпадают с ``docs/test_cases.md``.
"""

from __future__ import annotations

import re

import pytest
import requests

from conftest import (
    ERROR_404_SCHEMA,
    REQUEST_TIMEOUT,
    USER_LIST_SCHEMA,
    USER_SCHEMA,
    assert_json_response,
    assert_schema,
    validate_schema,
)

#: Полный набор полей пользователя по контракту.
EXPECTED_USER_FIELDS = {
    "id",
    "name",
    "username",
    "email",
    "address",
    "phone",
    "website",
    "company",
}

#: Поля вложенного объекта address.
EXPECTED_ADDRESS_FIELDS = {"street", "suite", "city", "zipcode", "geo"}

#: Поля вложенного объекта company.
EXPECTED_COMPANY_FIELDS = {"name", "catchPhrase", "bs"}


# ==========================================================================
# РАЗДЕЛ 1. Структура объекта пользователя
# ==========================================================================


def test_tc54_user_has_exactly_expected_top_level_fields(users_list):
    """TC-54. Каждый пользователь содержит ровно 8 полей верхнего уровня.

    Проверяются и пропущенные, и лишние поля: контракт должен быть
    стабильным в обе стороны.
    """
    for user in users_list:
        actual = set(user.keys())
        missing = EXPECTED_USER_FIELDS - actual
        extra = actual - EXPECTED_USER_FIELDS
        assert not missing, f"Пользователь id={user['id']}: нет полей {sorted(missing)}"
        assert not extra, f"Пользователь id={user['id']}: лишние поля {sorted(extra)}"


def test_tc55_user_types_match_contract(users_list):
    """TC-55. Типы полей пользователя соответствуют контракту.

    ``id`` — целое; ``name``, ``username``, ``email``, ``phone``, ``website`` —
    строки; ``address`` и ``company`` — вложенные объекты.
    """
    for user in users_list:
        assert isinstance(user["id"], int) and not isinstance(user["id"], bool), (
            f"id должен быть целым числом, получено {user['id']!r}"
        )
        for field in ("name", "username", "email", "phone", "website"):
            assert isinstance(user[field], str), (
                f"Поле {field} у id={user['id']} должно быть строкой, "
                f"получено {type(user[field]).__name__}"
            )
        assert isinstance(user["address"], dict), "address должен быть объектом"
        assert isinstance(user["company"], dict), "company должен быть объектом"


def test_tc56_user_ids_are_unique(users_list):
    """TC-56. Идентификаторы пользователей уникальны.

    Дубликат id сломал бы любой клиент, который строит словарь по id.
    """
    ids = [user["id"] for user in users_list]
    duplicates = {value for value in ids if ids.count(value) > 1}
    assert not duplicates, f"Найдены повторяющиеся id: {sorted(duplicates)}"


def test_tc57_user_ids_are_positive_and_sequential(users_list):
    """TC-57. Идентификаторы — положительные целые и идут без пропусков.

    Коллекция должна начинаться с 1 и быть непрерывной: 1, 2, 3, …, 10.
    """
    ids = sorted(user["id"] for user in users_list)
    assert all(isinstance(value, int) and value > 0 for value in ids), (
        f"Все id должны быть положительными целыми, получено {ids}"
    )
    assert ids == list(range(1, len(ids) + 1)), (
        f"Ожидался непрерывный ряд 1..{len(ids)}, получено {ids}"
    )


def test_tc58_all_required_string_fields_are_non_empty(users_list):
    """TC-58. Обязательные строковые поля не пусты и не состоят из пробелов."""
    for user in users_list:
        for field in ("name", "username", "email", "phone", "website"):
            value = user[field]
            assert value.strip(), (
                f"Пользователь id={user['id']}: поле {field} пустое"
            )


# ==========================================================================
# РАЗДЕЛ 2. Вложенность структур
# ==========================================================================


def test_tc59_address_has_exactly_expected_fields(users_list):
    """TC-59. Объект address содержит ровно 5 полей: street, suite, city,
    zipcode, geo."""
    for user in users_list:
        address = user["address"]
        actual = set(address.keys())
        assert actual == EXPECTED_ADDRESS_FIELDS, (
            f"id={user['id']}: состав полей address {sorted(actual)} "
            f"не совпадает с ожидаемым {sorted(EXPECTED_ADDRESS_FIELDS)}"
        )


def test_tc60_geo_nested_object_contract(users_list):
    """TC-60. Объект address.geo (третий уровень) содержит lat и lng.

    ОСОБЕННОСТЬ КОНТРАКТА: координаты отдаются **строками**, а не числами.
    Клиент, ожидающий число, получит ошибку при арифметике. Тест закрепляет
    текущее поведение и одновременно служит ранним предупреждением, если
    сервис исправит тип на числовой.
    """
    for user in users_list:
        geo = user["address"]["geo"]
        assert isinstance(geo, dict), f"id={user['id']}: geo должен быть объектом"
        assert set(geo.keys()) == {"lat", "lng"}, (
            f"id={user['id']}: состав полей geo {sorted(geo.keys())} != ['lat', 'lng']"
        )
        for axis in ("lat", "lng"):
            assert isinstance(geo[axis], str), (
                f"id={user['id']}: geo.{axis} должен быть строкой "
                f"(особенность API), получено {type(geo[axis]).__name__}"
            )
            # Строка должна быть корректным числом с плавающей точкой.
            float(geo[axis])  # выбросит ValueError, если это не число


def test_tc61_company_nested_object_contract(users_list):
    """TC-61. Объект company содержит ровно name, catchPhrase и bs."""
    for user in users_list:
        company = user["company"]
        actual = set(company.keys())
        assert actual == EXPECTED_COMPANY_FIELDS, (
            f"id={user['id']}: состав полей company {sorted(actual)} "
            f"не совпадает с {sorted(EXPECTED_COMPANY_FIELDS)}"
        )
        for field in EXPECTED_COMPANY_FIELDS:
            assert isinstance(company[field], str), (
                f"id={user['id']}: company.{field} должен быть строкой"
            )


def test_tc62_full_schema_validation_of_collection(users_list):
    """TC-62. Вся коллекция целиком проходит проверку по JSON-схеме.

    Схема USER_LIST_SCHEMA описывает три уровня вложенности и запрещает
    лишние поля (additionalProperties: false).
    """
    assert_schema(users_list, USER_LIST_SCHEMA)


def test_tc63_schema_helper_detects_violations():
    """TC-63. Самопроверка валидатора схем: он действительно ловит ошибки.

    Без этого теста «зелёный» прогон контрактных проверок ничего не доказывал
    бы: валидатор мог бы всегда возвращать пустой список ошибок.
    """
    # 1. Отсутствует обязательное поле.
    errors = validate_schema({"id": 1}, USER_SCHEMA)
    assert any("отсутствует обязательное поле" in e for e in errors), (
        "Валидатор не заметил отсутствие обязательных полей"
    )

    # 2. Неверный тип.
    bad = {k: "x" for k in EXPECTED_USER_FIELDS}
    bad["id"] = "не число"
    bad["address"] = {"street": "s", "suite": "s", "city": "c",
                      "zipcode": "z", "geo": {"lat": "1", "lng": "2"}}
    bad["company"] = {"name": "n", "catchPhrase": "c", "bs": "b"}
    errors = validate_schema(bad, USER_SCHEMA)
    assert any("ожидался тип 'integer'" in e for e in errors), (
        "Валидатор не заметил неверный тип id"
    )

    # 3. Лишнее поле.
    extra = {
        "id": 1, "name": "n", "username": "u", "email": "a@b.com",
        "phone": "1", "website": "w",
        "address": {"street": "s", "suite": "s", "city": "c", "zipcode": "z",
                    "geo": {"lat": "1", "lng": "2"}},
        "company": {"name": "n", "catchPhrase": "c", "bs": "b"},
        "unexpected": True,
    }
    errors = validate_schema(extra, USER_SCHEMA)
    assert any("неожиданные поля" in e for e in errors), (
        "Валидатор не заметил лишнее поле"
    )

    # 4. Корректный объект не должен давать ошибок.
    assert validate_schema(extra | {}, USER_SCHEMA) != []  # лишнее поле осталось
    clean = {k: v for k, v in extra.items() if k != "unexpected"}
    assert validate_schema(clean, USER_SCHEMA) == [], (
        f"Валидатор ошибочно забраковал корректный объект: "
        f"{validate_schema(clean, USER_SCHEMA)}"
    )


# ==========================================================================
# РАЗДЕЛ 3. Форматы значений
# ==========================================================================


@pytest.mark.parametrize(
    ("field", "pattern", "title"),
    [
        ("email", r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$", "email"),
        ("website", r"^[A-Za-z0-9.-]+\.[A-Za-z]{2,}$", "website"),
        ("username", r"^\S+$", "username без пробелов"),
    ],
    ids=["email", "website", "username"],
)
def test_tc64_value_formats(users_list, field, pattern, title):
    """TC-64. Форматы значений полей соответствуют контракту.

    Три тест-кейса: email, website и username (без пробелов).
    """
    compiled = re.compile(pattern)
    for user in users_list:
        value = user[field]
        assert compiled.match(value), (
            f"id={user['id']}: {title} = {value!r} не соответствует шаблону {pattern!r}"
        )


def test_tc65_zipcode_and_city_are_non_empty(users_list):
    """TC-65. Поля address.zipcode и address.city не пусты."""
    for user in users_list:
        address = user["address"]
        for field in ("zipcode", "city", "street", "suite"):
            assert isinstance(address[field], str) and address[field].strip(), (
                f"id={user['id']}: address.{field} пустое или не строка"
            )


def test_tc66_geo_coordinates_within_valid_range(users_list):
    """TC-66. Координаты geo лежат в допустимых пределах.

    Широта: −90…90, долгота: −180…180. Проверяется бизнес-корректность
    данных, а не только их тип.
    """
    for user in users_list:
        geo = user["address"]["geo"]
        lat, lng = float(geo["lat"]), float(geo["lng"])
        assert -90.0 <= lat <= 90.0, f"id={user['id']}: широта {lat} вне диапазона"
        assert -180.0 <= lng <= 180.0, f"id={user['id']}: долгота {lng} вне диапазона"


# ==========================================================================
# РАЗДЕЛ 4. Согласованность между эндпоинтами
# ==========================================================================


def test_tc67_individual_user_matches_collection_entry(api, users_list):
    """TC-67. Запись из коллекции совпадает с ответом GET /users/{id}.

    Два эндпоинта должны отдавать одни и те же данные. Расхождение —
    классический источник ошибок у клиентов, которые кэшируют коллекцию.
    """
    for user in users_list[:3]:
        single = assert_json_response(api.get(f"/users/{user['id']}"))
        assert single == user, (
            f"Данные для id={user['id']} различаются между /users и "
            f"/users/{user['id']}"
        )


@pytest.mark.parametrize("user_id", [1, 2, 3], ids=lambda v: f"user{v}")
def test_tc68_user_posts_nested_resource_contract(api, user_id):
    """TC-68. GET /users/{id}/posts — контракт вложенного ресурса.

    Три тест-кейса. Ответ — массив объектов с полями userId, id, title, body;
    поле userId совпадает с id из URL.
    """
    response = api.get(f"/users/{user_id}/posts")
    assert response.status_code == 200, (
        f"Ожидался 200, получен {response.status_code}"
    )
    posts = assert_json_response(response)
    assert isinstance(posts, list) and posts, "Ожидался непустой массив постов"

    assert_schema(
        posts,
        {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["userId", "id", "title", "body"],
                "properties": {
                    "userId": {"type": "integer"},
                    "id": {"type": "integer"},
                    "title": {"type": "string"},
                    "body": {"type": "string"},
                },
            },
        },
    )
    for post in posts:
        assert post["userId"] == user_id, (
            f"Пост id={post['id']} принадлежит пользователю {post['userId']}, "
            f"а запрошен {user_id}"
        )


# ==========================================================================
# РАЗДЕЛ 5. Контракт ответов об ошибках и заголовков
# ==========================================================================


def test_tc69_404_body_contract(api):
    """TC-69. Контракт тела 404-ответа — пустой объект без полей.

    ОСОБЕННОСТЬ КОНТРАКТА: тело ошибки не содержит ни ``error``, ни
    ``message``, ни ``status``. Клиент не может отличить «запись не найдена»
    от любой другой 404-ситуации. Проверяется схемой ERROR_404_SCHEMA.
    """
    for path in ("/users/9999", "/users/abc", "/nonexistent"):
        body = assert_json_response(api.get(path))
        assert_schema(body, ERROR_404_SCHEMA)
        assert body == {}, f"{path}: ожидался {{}}, получено {body!r}"


def test_tc70_delete_response_contract(api):
    """TC-70. Контракт ответа DELETE — 200 и тело ``{}``.

    ОСОБЕННОСТЬ: DELETE возвращает 200 с телом-объектом, а не 204 без тела.
    """
    response = api.delete("/users/1")
    assert response.status_code == 200
    assert assert_json_response(response) == {}


def test_tc71_post_response_contract(api, created_user_payload):
    """TC-71. Контракт ответа POST — эхо полей плюс id, тип application/json."""
    response = api.post("/users", json=created_user_payload)
    assert response.status_code == 201
    assert response.headers.get("Content-Type", "").startswith("application/json")

    body = assert_json_response(response)
    assert isinstance(body, dict)
    assert "id" in body, "POST-ответ обязан содержать id созданной записи"
    for field in created_user_payload:
        assert field in body, f"POST-ответ не содержит отправленное поле {field!r}"


@pytest.mark.parametrize("path", ["/users", "/users/1", "/users/9999"],
                         ids=["collection", "single", "notfound"])
def test_tc72_content_type_declares_utf8_charset(api, path):
    """TC-72. Content-Type содержит ``charset=utf-8``.

    Три тест-кейса. Без явной кодировки клиент может неверно декодировать
    не-ASCII символы (например, в поле name).
    """
    content_type = api.get(path).headers.get("Content-Type", "").lower()
    assert "charset=utf-8" in content_type, (
        f"{path}: ожидался charset=utf-8, получен {content_type!r}"
    )


def test_tc73_non_ascii_values_survive_round_trip(api):
    """TC-73. Кириллица в данных не искажается при передачи через API.

    Проверяется, что сервис и клиент одинаково работают с UTF-8: то, что
    отправлено в POST, возвращается в ответе без искажений.
    """
    payload = {"name": "Иван Петров", "username": "иван", "city": "Москва"}
    body = assert_json_response(api.post("/users", json=payload))
    for field, value in payload.items():
        assert body.get(field) == value, (
            f"Поле {field!r} искажено: отправлено {value!r}, получено {body.get(field)!r}"
        )


def test_tc74_api_is_reachable_and_stable(api_url):
    """TC-74. Базовый адрес API отвечает стабильно (3 запроса подряд).

    Проверка доступности объекта тестирования: если сервис «плавает»,
    результаты остальных тестов недостоверны.
    """
    codes = []
    for _ in range(3):
        response = requests.get(f"{api_url}/users/1", timeout=REQUEST_TIMEOUT)
        codes.append(response.status_code)
    assert codes == [200, 200, 200], f"Нестабильные ответы API: {codes}"


# Все тесты модуля относятся к набору API (см. маркеры в pytest.ini).
pytestmark = pytest.mark.api
