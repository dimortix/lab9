# -*- coding: utf-8 -*-
"""
Функциональные тесты REST API — аналог тестов Postman на Python.

Модуль повторяет логику коллекции ``postman/collection.json``:
позитивные сценарии (GET / POST / PUT / PATCH / DELETE), негативные сценарии
(404, 400/500, невалидный JSON, отсутствие обязательных полей), проверки
заголовков, структуры JSON и времени ответа.

Идентификаторы тестов (TC-xx) совпадают с таблицей ``docs/test_cases.md``.

Объект тестирования по умолчанию — публичный
``https://jsonplaceholder.typicode.com``. Адрес переопределяется переменной
окружения ``API_BASE_URL``::

    pytest -v                                              # публичный API
    API_BASE_URL=http://127.0.0.1:8090 pytest -v           # локальный мок
"""

from __future__ import annotations

import json

import pytest

from conftest import (
    ERROR_404_SCHEMA,
    MAX_RESPONSE_TIME,
    REQUEST_TIMEOUT,
    USER_LIST_SCHEMA,
    USER_SCHEMA,
    assert_json_response,
    assert_schema,
)

# ==========================================================================
# РАЗДЕЛ 1. GET — позитивные сценарии
# ==========================================================================


def test_tc01_get_user_returns_200(api):
    """TC-01. GET /users/1 — успешный запрос возвращает 200 OK."""
    response = api.get("/users/1")
    assert response.status_code == 200, (
        f"Ожидался 200, получен {response.status_code}: {response.text[:200]}"
    )


def test_tc02_get_user_content_type_is_json(api):
    """TC-02. GET /users/1 — заголовок Content-Type равен application/json."""
    response = api.get("/users/1")
    content_type = response.headers.get("Content-Type", "")
    assert content_type.startswith("application/json"), (
        f"Ожидался Content-Type application/json, получен {content_type!r}"
    )


def test_tc03_get_user_body_is_json_object(api):
    """TC-03. GET /users/1 — тело ответа является JSON-объектом (не массивом)."""
    body = assert_json_response(api.get("/users/1"))
    assert isinstance(body, dict), f"Ожидался объект, получен {type(body).__name__}"


def test_tc04_get_user_id_matches_request(api):
    """TC-04. GET /users/1 — поле id совпадает с запрошенным идентификатором."""
    body = assert_json_response(api.get("/users/1"))
    assert body["id"] == 1, f"Ожидался id=1, получен {body['id']!r}"


def test_tc05_get_user_name_is_non_empty_string(api):
    """TC-05. GET /users/1 — поле name непустая строка."""
    body = assert_json_response(api.get("/users/1"))
    assert isinstance(body["name"], str) and body["name"].strip(), (
        f"Поле name должно быть непустой строкой, получено {body['name']!r}"
    )


def test_tc06_get_user_email_is_valid(api):
    """TC-06. GET /users/1 — поле email похоже на корректный адрес.

    Проверяется регулярным выражением из схемы (см. conftest.USER_SCHEMA).
    """
    body = assert_json_response(api.get("/users/1"))
    assert_schema({"email": body["email"]}, {"type": "object", "properties": {
        "email": USER_SCHEMA["properties"]["email"]
    }})


@pytest.mark.parametrize("user_id", [1, 2, 3, 4, 5], ids=lambda v: f"user{v}")
def test_tc07_get_existing_users(api, user_id):
    """TC-07. GET /users/{id} — параметризованная проверка существующих записей.

    Пять отдельных тест-кейсов: для каждого id проверяются код ответа и
    совпадение поля id с запрошенным.
    """
    response = api.get(f"/users/{user_id}")
    assert response.status_code == 200
    assert response.json()["id"] == user_id


def test_tc08_get_user_response_time(api, assert_fast):
    """TC-08. GET /users/1 — время ответа укладывается в порог 3 секунды."""
    assert_fast(api.get("/users/1"))


def test_tc09_get_users_collection_returns_200(api):
    """TC-09. GET /users — коллекция отдаётся с кодом 200."""
    assert api.get("/users").status_code == 200


def test_tc10_get_users_collection_is_array(api):
    """TC-10. GET /users — тело ответа является JSON-массивом."""
    body = assert_json_response(api.get("/users"))
    assert isinstance(body, list), f"Ожидался массив, получен {type(body).__name__}"


def test_tc11_get_users_collection_has_ten_items(users_list):
    """TC-11. GET /users — в коллекции ровно 10 пользователей."""
    assert len(users_list) == 10, f"Ожидалось 10 записей, получено {len(users_list)}"


def test_tc12_get_users_limit_query_param(api):
    """TC-12. GET /users?_limit=3 — параметр _limit ограничивает выборку.

    Возможность json-server; на публичном API реально работает.
    """
    body = assert_json_response(api.get("/users?_limit=3"))
    assert isinstance(body, list) and len(body) == 3, (
        f"Ожидалось 3 записи, получено {len(body) if isinstance(body, list) else body}"
    )


def test_tc13_get_users_collection_matches_schema(users_list):
    """TC-13. GET /users — каждый элемент коллекции соответствует схеме."""
    assert_schema(users_list, USER_LIST_SCHEMA)


# ==========================================================================
# РАЗДЕЛ 2. GET — негативные сценарии (404)
# ==========================================================================


@pytest.mark.parametrize(
    "user_id",
    ["9999", "0", "-1", "abc", "11", "1.5"],
    ids=["id9999", "id0", "negative", "nonnumeric", "outofrange", "float"],
)
def test_tc14_get_nonexistent_user_returns_404(api, user_id):
    """TC-14. GET /users/{id} — несуществующий/некорректный id даёт 404.

    Шесть тест-кейсов: id за пределами коллекции, нулевой, отрицательный,
    нечисловой, следующий за последним (11) и дробный.
    """
    response = api.get(f"/users/{user_id}")
    assert response.status_code == 404, (
        f"Для id={user_id!r} ожидался 404, получен {response.status_code}"
    )


def test_tc15_get_nonexistent_user_body_is_empty_object(api):
    """TC-15. GET /users/9999 — тело 404-ответа равно пустому объекту ``{}``.

    ОСОБЕННОСТЬ API: сервис не возвращает ни ``error``, ни ``message`` —
    только ``{}``, поэтому клиент не может понять причину отказа.
    Проверяется схемой ERROR_404_SCHEMA (объект без полей).
    """
    body = assert_json_response(api.get("/users/9999"))
    assert body == {}, f"Ожидался пустой объект, получен {body!r}"
    assert_schema(body, ERROR_404_SCHEMA)


def test_tc16_get_nonexistent_user_content_type_is_json(api):
    """TC-16. GET /users/9999 — 404 всё равно отдаётся как application/json."""
    response = api.get("/users/9999")
    assert response.headers.get("Content-Type", "").startswith("application/json")


def test_tc17_get_unknown_route_returns_404(api):
    """TC-17. GET /nonexistent — неизвестный маршрут даёт 404."""
    assert api.get("/nonexistent").status_code == 404


def test_tc18_get_nonexistent_user_response_time(api, assert_fast):
    """TC-18. GET /users/9999 — 404 приходит так же быстро, как успешный ответ."""
    assert_fast(api.get("/users/9999"))


# ==========================================================================
# РАЗДЕЛ 3. POST — создание пользователя
# ==========================================================================


def test_tc19_post_create_user_returns_201(api, created_user_payload):
    """TC-19. POST /users — корректный запрос возвращает 201 Created."""
    response = api.post("/users", json=created_user_payload)
    assert response.status_code == 201, (
        f"Ожидался 201, получен {response.status_code}: {response.text[:200]}"
    )


def test_tc20_post_echoes_sent_fields(api, created_user_payload):
    """TC-20. POST /users — ответ содержит все отправленные поля (эхо)."""
    body = assert_json_response(api.post("/users", json=created_user_payload))
    for field, value in created_user_payload.items():
        assert field in body, f"Поле {field!r} отсутствует в ответе"
        assert body[field] == value, (
            f"Поле {field!r}: отправлено {value!r}, получено {body[field]!r}"
        )


def test_tc21_post_response_contains_id(api, created_user_payload):
    """TC-21. POST /users — в ответе есть целочисленный id новой записи."""
    body = assert_json_response(api.post("/users", json=created_user_payload))
    assert "id" in body, "В ответе отсутствует поле id"
    assert isinstance(body["id"], int) and not isinstance(body["id"], bool), (
        f"id должен быть целым числом, получено {body['id']!r}"
    )


def test_tc22_post_response_content_type(api, created_user_payload):
    """TC-22. POST /users — ответ помечен как application/json."""
    response = api.post("/users", json=created_user_payload)
    assert response.headers.get("Content-Type", "").startswith("application/json")


def test_tc23_post_returns_location_header(api, created_user_payload):
    """TC-23. POST /users — присутствует заголовок Location с адресом записи.

    ОСОБЕННОСТЬ API: заголовок указывает на ``/users/11``, хотя физически
    запись не сохраняется — при повторном GET этого адреса будет 404.
    """
    response = api.post("/users", json=created_user_payload)
    location = response.headers.get("Location")
    assert location, "Заголовок Location отсутствует в ответе 201"
    assert location.endswith("/users/11"), (
        f"Ожидался Location, оканчивающийся на /users/11, получен {location!r}"
    )


def test_tc24_post_response_time(api, created_user_payload, assert_fast):
    """TC-24. POST /users — время ответа укладывается в порог."""
    assert_fast(api.post("/users", json=created_user_payload))


def test_tc25_post_without_optional_fields_returns_201(api):
    """TC-25. POST /users — запрос только с одним полем всё равно даёт 201.

    НЕГАТИВНЫЙ СЦЕНАРИЙ / НАЙДЕННАЯ ОСОБЕННОСТЬ: сервер не проверяет
    обязательные поля. Тест фиксирует фактическое поведение, а не ожидаемое
    «правильное» — расхождение разобрано в docs/analysis.md.
    """
    response = api.post("/users", json={"name": "Только имя"})
    assert response.status_code == 201, (
        "Сервер неожиданно начал валидировать обязательные поля: "
        f"получен {response.status_code}"
    )


def test_tc26_post_with_empty_body_returns_201(api):
    """TC-26. POST /users — пустое тело ``{}`` тоже даёт 201.

    НАЙДЕННАЯ ОСОБЕННОСТЬ: запись «создаётся» вообще без данных.
    """
    response = api.post("/users", json={})
    assert response.status_code == 201
    assert response.json().get("id") == 11


def test_tc27_post_with_invalid_json_returns_500(api):
    """TC-27. POST /users — битый JSON приводит к 500 (а не к 400).

    НАЙДЕННЫЙ ДЕФЕКТ публичного API: некорректный ввод клиента вызывает
    внутреннюю ошибку сервера с HTML-трассировкой. Корректным ответом был бы
    400 Bad Request. Тест закрепляет текущее (дефектное) поведение, чтобы
    отследить момент исправления.
    """
    response = api.post(
        "/users",
        data="{invalid json",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 500, (
        f"Ожидался 500 (текущее поведение), получен {response.status_code}"
    )


def test_tc28_post_with_invalid_json_returns_html_trace(api):
    """TC-28. POST /users (битый JSON) — ответ приходит как text/html.

    НАЙДЕННЫЙ ДЕФЕКТ (продолжение TC-27): сервер отдаёт HTML-страницу
    с трассировкой стека вместо JSON-описания ошибки. Это ещё и утечка
    внутренних деталей реализации (имена модулей и функции).
    """
    response = api.post(
        "/users",
        data="{invalid json",
        headers={"Content-Type": "application/json"},
    )
    content_type = response.headers.get("Content-Type", "")
    assert content_type.startswith("text/html"), (
        f"Ожидался text/html, получен {content_type!r}"
    )
    # Убеждаемся, что в теле действительно есть следы трассировки.
    assert "Error" in response.text, "В теле ответа нет описания ошибки"


def test_tc29_post_without_content_type_ignores_body(api):
    """TC-29. POST /users без Content-Type — тело не разбирается.

    ОСОБЕННОСТЬ API: если заголовок Content-Type не задан, сервер не парсит
    тело и возвращает только ``{"id": 11}``. Клиент при этом получает 201 и
    может решить, что данные сохранены.
    """
    response = api.post("/users", data=json.dumps({"name": "Без заголовка"}))
    assert response.status_code == 201
    body = response.json()
    assert "name" not in body, (
        f"Тело неожиданно разобрано: {body!r} — поведение API изменилось"
    )
    assert body.get("id") == 11


def test_tc30_post_form_urlencoded_is_parsed(api):
    """TC-30. POST /users с form-urlencoded — тело разбирается как форма.

    ОСОБЕННОСТЬ API: сервис принимает не только JSON. Это расширяет
    поверхность атаки (клиент может отправить данные в неожиданном формате).
    """
    response = api.post("/users", data={"name": "Иван", "job": "QA"})
    assert response.status_code == 201
    body = response.json()
    assert body.get("name") == "Иван"
    assert body.get("job") == "QA"


def test_tc31_post_with_wrong_field_types_returns_201(api):
    """TC-31. POST /users — поля неверного типа принимаются без ошибок.

    НЕГАТИВНЫЙ СЦЕНАРИЙ: ``name`` передан числом, ``email`` — тоже. Сервер
    не проверяет типы и отвечает 201. Контракт не защищён от «грязных» данных.
    """
    response = api.post("/users", json={"name": 12345, "email": 999})
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == 12345
    assert body["email"] == 999


def test_tc32_post_json_array_returns_201(api):
    """TC-32. POST /users с JSON-массивом — 201 и преобразование в объект.

    ОСОБЕННОСТЬ API: массив ``[1, 2]`` превращается в объект с числовыми
    ключами ``{"0": 1, "1": 2}`` (семантика spread-оператора JavaScript).
    """
    response = api.post("/users", json=[1, 2])
    assert response.status_code == 201
    body = response.json()
    assert body.get("0") == 1 and body.get("1") == 2, f"Получено {body!r}"


# ==========================================================================
# РАЗДЕЛ 4. PUT / PATCH — обновление пользователя
# ==========================================================================


def test_tc33_put_update_user_returns_200(api, created_user_payload):
    """TC-33. PUT /users/1 — обновление существующей записи возвращает 200."""
    response = api.put("/users/1", json=created_user_payload)
    assert response.status_code == 200, (
        f"Ожидался 200, получен {response.status_code}: {response.text[:200]}"
    )


def test_tc34_put_echoes_updated_fields(api, created_user_payload):
    """TC-34. PUT /users/1 — ответ содержит обновлённые значения полей."""
    body = assert_json_response(api.put("/users/1", json=created_user_payload))
    for field, value in created_user_payload.items():
        assert body.get(field) == value, (
            f"Поле {field!r}: ожидалось {value!r}, получено {body.get(field)!r}"
        )


def test_tc35_put_keeps_id_from_url(api):
    """TC-35. PUT /users/1 — в ответе id равен id из URL."""
    body = assert_json_response(api.put("/users/1", json={"name": "Обновление"}))
    assert body.get("id") == 1, f"Ожидался id=1, получен {body.get('id')!r}"


def test_tc36_put_is_not_persisted(api_url):
    """TC-36. PUT /users/1 не сохраняет изменения (проверка через новый GET).

    ВАЖНАЯ ОСОБЕННОСТЬ: публичный API только имитирует запись. После PUT
    повторный GET возвращает исходные данные. Тест явно это фиксирует —
    иначе легко решить, что «обновление работает».
    """
    import requests

    original = requests.get(f"{api_url}/users/1", timeout=REQUEST_TIMEOUT).json()
    marker = "ЭТО-ОБНОВЛЕНИЕ-НЕ-ДОЛЖНО-СОХРАНИТЬСЯ"
    requests.put(f"{api_url}/users/1", json={"name": marker}, timeout=REQUEST_TIMEOUT)
    after = requests.get(f"{api_url}/users/1", timeout=REQUEST_TIMEOUT).json()

    assert after == original, (
        "Данные изменились после PUT — значит, объект тестирования стал "
        "поддерживать реальное сохранение. Ожидания теста нужно пересмотреть."
    )
    assert after["name"] != marker


def test_tc37_put_nonexistent_user_returns_500(api):
    """TC-37. PUT /users/9999 — 500 вместо ожидаемого 404.

    НАЙДЕННЫЙ ДЕФЕКТ: обновление несуществующей записи вызывает внутреннюю
    ошибку сервера (``TypeError: Cannot read properties of undefined``).
    Корректным ответом был бы 404 Not Found. Асимметрия с GET /users/9999,
    который честно возвращает 404, — признак неполной обработки ошибок.
    """
    response = api.put("/users/9999", json={"name": "Призрак"})
    assert response.status_code == 500, (
        f"Ожидался 500 (текущее дефектное поведение), получен {response.status_code}"
    )


def test_tc38_put_with_invalid_json_returns_500(api):
    """TC-38. PUT /users/1 — битый JSON даёт 500 вместо 400.

    НАЙДЕННЫЙ ДЕФЕКТ, аналогичный TC-27, но для метода PUT.
    """
    response = api.put(
        "/users/1",
        data="{broken",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 500


def test_tc39_patch_merges_with_existing_record(api):
    """TC-39. PATCH /users/1 — частичное обновление СЛИВАЕТСЯ с записью.

    ОСОБЕННОСТЬ API: в отличие от PUT, PATCH сохраняет поля, которых нет
    в запросе (username, email, address остаются от исходной записи).
    """
    original = api.get("/users/1").json()
    response = api.patch("/users/1", json={"name": "Частичное обновление"})
    assert response.status_code == 200
    body = response.json()

    assert body["name"] == "Частичное обновление"
    assert body["username"] == original["username"], (
        "PATCH не сохранил поле username — поведение API изменилось"
    )
    assert body["email"] == original["email"]
    assert "address" in body


def test_tc40_patch_nonexistent_user_returns_200(api):
    """TC-40. PATCH /users/9999 — 200 с телом запроса (а не 404 и не 500).

    ОСОБЕННОСТЬ API: асимметрия обработки ошибок. GET несуществующей записи
    даёт 404, PUT — 500, а PATCH — 200. Клиент не может определить, что
    обновлять было нечего.
    """
    response = api.patch("/users/9999", json={"name": "Призрак"})
    assert response.status_code == 200, (
        f"Ожидался 200 (текущее поведение), получен {response.status_code}"
    )
    assert response.json() == {"name": "Призрак"}


# ==========================================================================
# РАЗДЕЛ 5. DELETE — удаление пользователя
# ==========================================================================


def test_tc41_delete_user_returns_200(api):
    """TC-41. DELETE /users/1 — удаление возвращает 200 OK.

    Особенность: публичный API отвечает 200, а не 204 No Content,
    хотя тело ответа пустое.
    """
    response = api.delete("/users/1")
    assert response.status_code == 200, (
        f"Ожидался 200, получен {response.status_code}"
    )


def test_tc42_delete_user_body_is_empty_object(api):
    """TC-42. DELETE /users/1 — тело ответа равно ``{}``."""
    body = assert_json_response(api.delete("/users/1"))
    assert body == {}, f"Ожидался пустой объект, получен {body!r}"


def test_tc43_delete_response_content_type(api):
    """TC-43. DELETE /users/1 — ответ помечен как application/json."""
    response = api.delete("/users/1")
    assert response.headers.get("Content-Type", "").startswith("application/json")


def test_tc44_delete_is_idempotent_for_missing_user(api):
    """TC-44. DELETE /users/9999 — удаление несуществующей записи тоже даёт 200.

    ОСОБЕННОСТЬ API: сервис идемпотентен, но не сообщает клиенту, что
    удалять было нечего (ожидался бы 404). Тест фиксирует это поведение.
    """
    first = api.delete("/users/9999")
    second = api.delete("/users/9999")
    assert first.status_code == 200
    assert second.status_code == 200, (
        "Повторное удаление вернуло другой код — идемпотентность нарушена"
    )


def test_tc45_delete_response_time(api, assert_fast):
    """TC-45. DELETE /users/1 — время ответа укладывается в порог."""
    assert_fast(api.delete("/users/1"))


# ==========================================================================
# РАЗДЕЛ 6. Сквозные проверки (заголовки, методы, корень)
# ==========================================================================


def test_tc46_root_endpoint_returns_html(api):
    """TC-46. GET / — корневой маршрут отдаёт 200 и HTML, а не JSON.

    Проверка «неожиданного» типа содержимого: клиент, ожидающий от API
    только JSON, на корневом маршруте получит HTML-страницу.
    """
    response = api.get("/")
    assert response.status_code == 200
    assert response.headers.get("Content-Type", "").startswith("text/html"), (
        f"Ожидался text/html, получен {response.headers.get('Content-Type')!r}"
    )


def test_tc47_options_returns_204(api):
    """TC-47. OPTIONS /users/1 — предварительный запрос CORS даёт 204."""
    response = api.request("OPTIONS", "/users/1")
    assert response.status_code == 204, (
        f"Ожидался 204, получен {response.status_code}"
    )


def test_tc48_head_returns_200_without_body(api):
    """TC-48. HEAD /users/1 — 200 и пустое тело ответа."""
    response = api.request("HEAD", "/users/1")
    assert response.status_code == 200
    assert response.text == "", "HEAD-ответ не должен содержать тело"


@pytest.mark.parametrize(
    ("method", "path"),
    [("POST", "/users/1"), ("PUT", "/users"), ("DELETE", "/users")],
    ids=["post_to_item", "put_to_collection", "delete_to_collection"],
)
def test_tc49_unsupported_method_returns_404(api, method, path):
    """TC-49. Метод не соответствует маршруту — 404 (а не 405).

    Три тест-кейса. ОСОБЕННОСТЬ API: вместо 405 Method Not Allowed сервис
    отвечает 404, что затрудняет диагностику на стороне клиента.
    """
    response = api.request(method, path, json={})
    assert response.status_code == 404, (
        f"{method} {path}: ожидался 404, получен {response.status_code}"
    )


def test_tc50_trace_method_not_allowed(api):
    """TC-50. TRACE /users/1 — единственный метод, дающий 405.

    ОСОБЕННОСТЬ API: TRACE обрабатывается иначе, чем остальные
    неподдерживаемые методы (см. TC-49).
    """
    response = api.request("TRACE", "/users/1")
    assert response.status_code == 405, (
        f"Ожидался 405, получен {response.status_code}"
    )


def test_tc51_qos_response_time_of_collection(api, assert_fast):
    """TC-51. GET /users — время ответа коллекции укладывается в порог."""
    assert_fast(api.get("/users"))


def test_tc52_json_schema_of_single_user(api):
    """TC-52. GET /users/1 — полная проверка JSON-схемы пользователя.

    Контрольная точка для API_BASE_URL: и публичный сервис, и локальный мок
    должны проходить эту проверку одинаково.
    """
    assert_schema(assert_json_response(api.get("/users/1")), USER_SCHEMA)


def test_tc53_response_threshold_constant_is_sane():
    """TC-53. Самопроверка: порог времени ответа задан разумно.

    Защита от случайного изменения константы MAX_RESPONSE_TIME на значение,
    при котором проверки производительности перестанут что-либо ловить.
    """
    assert 0.5 <= MAX_RESPONSE_TIME <= 10.0, (
        f"MAX_RESPONSE_TIME={MAX_RESPONSE_TIME} вне разумного диапазона 0.5..10 с"
    )


# Все тесты модуля относятся к набору API (см. маркеры в pytest.ini).
pytestmark = pytest.mark.api
