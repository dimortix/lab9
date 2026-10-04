#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Локальный мок-сервер публичного REST API jsonplaceholder.typicode.com
=====================================================================

Назначение
----------
Публичный API ``https://jsonplaceholder.typicode.com`` доступен только при
наличии интернета. Чтобы автотесты лабораторной работы №5 были
воспроизводимы в любой аудитории (и на машине проверяющего без сети),
этот мок повторяет **реально зафиксированный** контракт публичного сервиса.

Данные для коллекции ``/users`` (10 пользователей) были получены реальным
запросом ``GET https://jsonplaceholder.typicode.com/users`` и сохранены в
``mock_server/users_data.json`` — то есть мок отдаёт те же самые значения
полей, что и публичный API, а не «похожие» выдуманные.

ВАЖНО: мок намеренно воспроизводит не только «правильное» поведение, но и
найденные при исследовании публичного API особенности/дефекты. Иначе один и
тот же набор тестов не мог бы одинаково проходить и против публичного API,
и против мока. Все воспроизводимые особенности перечислены ниже и разобраны
в ``docs/analysis.md``.

Зафиксированный контракт публичного API (проверен curl'ом)
----------------------------------------------------------
| Запрос                      | Ответ публичного API                        |
|-----------------------------|---------------------------------------------|
| GET /users                  | 200, массив из 10 пользователей             |
| GET /users?_limit=N         | 200, первые N пользователей                 |
| GET /users/1                | 200, объект пользователя (плоский + вложенность) |
| GET /users/9999             | 404, тело — пустой объект ``{}``            |
| GET /users/0, /users/-1     | 404, тело — ``{}``                          |
| GET /users/abc              | 404, тело — ``{}``                          |
| GET /users/11               | 404, тело — ``{}`` (всего записей 10)       |
| POST /users (валидный JSON) | 201, эхо тела + ``id: 11``, заголовок Location |
| POST /users (без тела)      | 201, ``{"id": 11}`` — валидации нет         |
| POST /users (только name)   | 201 — обязательные поля не проверяются      |
| POST /users (JSON-массив)   | 201, ``{"0": …, "1": …, "id": 11}``         |
| POST /users (битый JSON)    | **500** + HTML-трассировка (а не 400!)      |
| POST /users (без Content-Type) | 201, ``{"id": 11}`` — тело не разбирается |
| POST /users (form-urlencoded)  | 201, ``{"name": "Ivan", "job": "QA", "id": 11}`` |
| PUT /users/1                | 200, тело запроса + ``id`` из URL           |
| PUT /users/9999             | **500** + HTML-трассировка (а не 404!)      |
| PATCH /users/1              | 200, СЛИЯНИЕ с текущей записью              |
| PATCH /users/9999           | 200, только тело запроса (ни 404, ни 500)   |
| DELETE /users/1             | 200, тело ``{}``                            |
| DELETE /users/9999          | 200, тело ``{}`` (идемпотентно, без 404)    |

Запуск
------
    python mock_server/app.py
    # сервер поднимется на http://127.0.0.1:8090

Порт 8090 выбран намеренно (не 5000/8000), чтобы не конфликтовать с другими
лабораторными работами курса. Порт можно переопределить переменной окружения
``MOCK_PORT``.
"""

from __future__ import annotations

import json
import os
import pathlib

from flask import Flask, Response, jsonify, request

# --------------------------------------------------------------------------
# Пути и константы
# --------------------------------------------------------------------------

BASE_DIR = pathlib.Path(__file__).resolve().parent
DATA_FILE = BASE_DIR / "users_data.json"

# Порт по умолчанию — 8090 (см. README и docs/).
DEFAULT_PORT = 8090

# json-server (движок публичного jsonplaceholder) всегда присваивает новым
# записям id = 11, независимо от тела запроса. Это зафиксировано реальным
# запросом и воспроизводится здесь для полной совместимости.
NEW_RECORD_ID = 11

app = Flask(__name__)
# Не сортируем ключи и сохраняем читаемый вывод (json-server отдаёт 2 пробела).
app.json.sort_keys = False
app.config["JSON_AS_ASCII"] = False


def load_users() -> list[dict]:
    """Читает эталонный список пользователей, снятый с публичного API."""
    with DATA_FILE.open(encoding="utf-8") as fh:
        return json.load(fh)


# Данные загружаются один раз при старте. Мок не хранит состояние между
# запросами: POST/PUT/DELETE не изменяют коллекцию — ровно так же ведёт себя
# публичный jsonplaceholder (он read-only и только имитирует запись).
USERS: list[dict] = load_users()
USERS_BY_ID: dict[int, dict] = {user["id"]: user for user in USERS}


def json_response(payload, status: int = 200, headers: dict | None = None) -> Response:
    """Формирует ответ в том же виде, что и публичный API.

    Публичный сервис отдаёт ``Content-Type: application/json; charset=utf-8``
    и тело с отступом в 2 пробела — это важно, потому что тесты проверяют
    заголовок Content-Type.
    """
    body = json.dumps(payload, ensure_ascii=False, indent=2)
    resp = Response(body, status=status, mimetype="application/json")
    resp.headers["Content-Type"] = "application/json; charset=utf-8"
    if headers:
        for key, value in headers.items():
            resp.headers[key] = value
    return resp


def express_style_error(exc_text: str) -> Response:
    """Воспроизводит ответ Express при необработанном исключении.

    Публичный jsonplaceholder на битый JSON и на ``PUT`` несуществующей
    записи отвечает **500** и HTML-страницей с трассировкой стека
    (``Content-Type: text/html; charset=utf-8``). Это реальный дефект
    публичного сервиса, причём двойной:

    1. ошибка клиента (битый JSON) приводит к ошибке сервера 500 вместо 400;
    2. в ответ попадает трассировка с внутренними путями вида
       ``/app/node_modules/body-parser/lib/types/json.js`` —
       раскрытие деталей реализации (information disclosure).

    Мок повторяет обе особенности, потому что тесты (``postman/collection.json``,
    запрос 2.3) проверяют их наличие. Пути в трассировке — синтетические
    маркеры, повторяющие форму реального ответа, а не настоящие пути этой
    машины: мок не должен утекать данные того компьютера, где он запущен.
    """
    stack = (
        "SyntaxError: Unexpected token\n"
        "    at JSON.parse (&lt;anonymous&gt;)\n"
        "    at parse (/app/node_modules/body-parser/lib/types/json.js:89:19)\n"
        "    at /app/node_modules/body-parser/lib/read.js:121:18\n"
        "    at invokeCallback (/app/node_modules/body-parser/node_modules/raw-body/index.js:224:16)\n"
        "    at IncomingMessage.onEnd (node:internal/streams/readable:1764:7)\n"
        "    at process.processTicksAndRejections (node:internal/process/task_queues:90:21)"
    )
    html = (
        '<!DOCTYPE html>\n<html lang="en">\n<head>\n'
        '<meta charset="utf-8">\n<title>Error</title>\n</head>\n<body>\n'
        f"<pre>Error: {exc_text}<br>{stack}</pre>\n</body>\n</html>\n"
    )
    resp = Response(html, status=500)
    resp.headers["Content-Type"] = "text/html; charset=utf-8"
    return resp


def parse_body() -> tuple[dict, Response | None]:
    """Разбирает тело запроса ровно так, как это делает публичный jsonplaceholder.

    Поведение зафиксировано реальными запросами и зависит от заголовка
    ``Content-Type``:

    =================================== ====================================
    Content-Type запроса               Что попадает в «тело» на сервере
    =================================== ====================================
    ``application/json``, валидный     разобранный JSON-объект
    ``application/json``, массив       объект с индексами: ``[1,2]`` → ``{"0":1,"1":2}``
    ``application/json``, битый JSON   ошибка → ответ **500** (а не 400!)
    ``application/x-www-form-urlencoded`` разобранная форма: ``name=Ivan`` → ``{"name":"Ivan"}``
    отсутствует / другой               тело НЕ разбирается вообще → ``{}``
    =================================== ====================================

    :return: кортеж ``(payload, error_response)``. Если ``error_response``
             не ``None``, его нужно немедленно вернуть клиенту.
    """
    raw_body = request.get_data(as_text=True)
    content_type = (request.headers.get("Content-Type") or "").lower()

    # --- 1. JSON ----------------------------------------------------------
    if "application/json" in content_type:
        if not raw_body.strip():
            return {}, None
        try:
            parsed = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            return {}, express_style_error(
                f"SyntaxError: {exc.msg} in JSON at position {exc.pos}"
            )
        if isinstance(parsed, dict):
            return dict(parsed), None
        if isinstance(parsed, list):
            # Семантика spread-оператора: {...[1, 2]} === {0: 1, 1: 2}.
            return {str(idx): value for idx, value in enumerate(parsed)}, None
        # Скаляр в теле — json-server трактует как пустой объект.
        return {}, None

    # --- 2. Форма ---------------------------------------------------------
    if "application/x-www-form-urlencoded" in content_type:
        return {key: value for key, value in request.form.items()}, None

    # --- 3. Content-Type не задан: тело игнорируется ----------------------
    return {}, None


# --------------------------------------------------------------------------
# GET /users — коллекция
# --------------------------------------------------------------------------


@app.get("/users")
def list_users() -> Response:
    """GET /users — список пользователей.

    Поддерживает query-параметр ``_limit`` (возможность json-server), который
    реально работает и на публичном API.
    """
    limit_raw = request.args.get("_limit")
    result = USERS
    if limit_raw is not None:
        try:
            result = USERS[: max(0, int(limit_raw))]
        except ValueError:
            # json-server игнорирует нечисловой _limit и отдаёт всё.
            result = USERS
    return json_response(result, 200)


# --------------------------------------------------------------------------
# GET /users/<id> — один пользователь
# --------------------------------------------------------------------------


@app.get("/users/<user_id>")
def get_user(user_id: str) -> Response:
    """GET /users/{id}.

    Особенность публичного API: и для несуществующего id, и для нечислового id
    возвращается 404 с телом ``{}`` — без описания ошибки. Воспроизводим.
    """
    if not user_id.isdigit():
        return json_response({}, 404)
    user = USERS_BY_ID.get(int(user_id))
    if user is None:
        return json_response({}, 404)
    return json_response(user, 200)


# --------------------------------------------------------------------------
# GET /users/<id>/posts — вложенный ресурс (только для пользователя 1)
# --------------------------------------------------------------------------


@app.get("/users/<user_id>/posts")
def get_user_posts(user_id: str) -> Response:
    """GET /users/{id}/posts — вложенный ресурс.

    Публичный API отдаёт массив постов; для мока достаточно проверить, что
    структура ответа — массив объектов с полями userId/id/title/body.
    """
    if not user_id.isdigit() or int(user_id) not in USERS_BY_ID:
        return json_response({}, 404)
    posts = [
        {
            "userId": int(user_id),
            "id": idx,
            "title": f"mock post {idx} for user {user_id}",
            "body": "mock body",
        }
        for idx in range(1, 3)
    ]
    return json_response(posts, 200)


# --------------------------------------------------------------------------
# POST /users — создание
# --------------------------------------------------------------------------


@app.post("/users")
def create_user() -> Response:
    """POST /users — имитация создания пользователя.

    Воспроизводимые особенности публичного API:

    1. Код ответа — **201**, заголовок ``Location: <base>/users/11``.
    2. Тело ответа — эхо присланного тела плюс ``id: 11``.
    3. **Валидации входных данных нет вообще**: запрос без тела или без
       обязательных полей всё равно возвращает 201. Это зафиксировано и
       проверяется негативными тестами как фактическое поведение сервиса.
    4. Битый JSON при ``Content-Type: application/json`` → **500**, а не 400
       (дефект публичного сервиса, см. ``docs/analysis.md``).
    5. Запрос без ``Content-Type: application/json`` → 201, но тело в ответ
       не попадает, потому что сервер его не разбирает.
    """
    payload, error = parse_body()
    if error is not None:
        return error

    created = dict(payload)
    created["id"] = NEW_RECORD_ID
    location = f"{request.host_url.rstrip('/')}/users/{NEW_RECORD_ID}"
    return json_response(created, 201, headers={"Location": location})


# --------------------------------------------------------------------------
# PUT /users/<id> — полное обновление
# --------------------------------------------------------------------------


@app.put("/users/<user_id>")
def update_user(user_id: str) -> Response:
    """PUT /users/{id} — имитация полного обновления.

    Воспроизводимые особенности:

    1. Для существующего id — **200** и тело запроса плюс ``id`` из URL.
       Публичный API не сохраняет изменения, поэтому PUT фактически
       не идемпотентен по состоянию.
    2. Для несуществующего id — **500** с HTML-трассировкой вместо 404.
       Это реальный дефект публичного сервиса (``TypeError: Cannot read
       properties of undefined (reading 'id')``), и он воспроизводится
       намеренно, чтобы негативный тест был переносимым.
    """
    payload, error = parse_body()
    if error is not None:
        return error

    if not user_id.isdigit() or int(user_id) not in USERS_BY_ID:
        return express_style_error(
            "TypeError: Cannot read properties of undefined (reading 'id')"
        )

    updated = dict(payload)
    updated["id"] = int(user_id)
    return json_response(updated, 200)


# --------------------------------------------------------------------------
# PATCH /users/<id> — частичное обновление
# --------------------------------------------------------------------------


@app.patch("/users/<user_id>")
def patch_user(user_id: str) -> Response:
    """PATCH /users/{id} — частичное обновление (слияние с текущей записью).

    Воспроизводимые особенности:

    1. Для существующего id — **200** и результат слияния: поля, которых нет
       в запросе, сохраняются из текущей записи.
    2. Для несуществующего id — тоже **200**, но без слияния: возвращается
       только тело запроса. Никакого 404 и никакого 500 (в отличие от PUT) —
       асимметрия поведения публичного API, зафиксирована реальным запросом.
    """
    payload, error = parse_body()
    if error is not None:
        return error

    existing = USERS_BY_ID.get(int(user_id)) if user_id.isdigit() else None
    if existing is None:
        return json_response(dict(payload), 200)

    merged = {**existing, **payload}
    merged["id"] = existing["id"]
    return json_response(merged, 200)


# --------------------------------------------------------------------------
# DELETE /users/<id> — удаление
# --------------------------------------------------------------------------


@app.delete("/users/<user_id>")
def delete_user(user_id: str) -> Response:
    """DELETE /users/{id} — всегда 200 с телом ``{}``.

    Особенность: публичный API отвечает 200 даже на удаление несуществующей
    записи (никакого 404). Воспроизводим — это проверяется тестом на
    идемпотентность DELETE.
    """
    return json_response({}, 200)


# --------------------------------------------------------------------------
# Служебные маршруты
# --------------------------------------------------------------------------


@app.get("/")
def index() -> Response:
    """Корневой маршрут.

    Публичный jsonplaceholder на ``GET /`` отдаёт **HTML**-страницу
    (``Content-Type: text/html; charset=UTF-8``), а не JSON. Мок повторяет
    это, потому что соответствующий тест проверяет тип содержимого.
    """
    html = (
        "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n"
        "<meta charset=\"utf-8\">\n<title>JSONPlaceholder (mock)</title>\n</head>\n"
        "<body>\n<h1>JSONPlaceholder — локальный мок</h1>\n"
        "<p>Для лабораторной работы №5 по тестированию ПО.</p>\n"
        "<ul>\n"
        "<li><a href=\"/users\">/users</a></li>\n"
        "<li><a href=\"/users/1\">/users/1</a></li>\n"
        "<li><a href=\"/health\">/health</a></li>\n"
        "</ul>\n</body>\n</html>\n"
    )
    resp = Response(html, status=200)
    resp.headers["Content-Type"] = "text/html; charset=UTF-8"
    return resp


@app.get("/health")
def health() -> Response:
    """Проверка живости мока — используется в scripts/run_all.sh."""
    return json_response({"status": "ok", "users": len(USERS)}, 200)


@app.before_request
def handle_preflight():
    """OPTIONS обрабатывается так же, как у публичного API — ответ 204.

    Реальный сервис на ``OPTIONS /users/1`` отдаёт ``204`` с заголовком
    ``Access-Control-Allow-Methods: GET,HEAD,PUT,PATCH,POST,DELETE``
    (это делает CORS-middleware Express). Flask по умолчанию ответил бы 200.
    """
    if request.method == "OPTIONS":
        resp = Response("", status=204, mimetype="application/json")
        # Ответ 204 не должен нести тело и не должен объявлять Content-Type —
        # публичный API на OPTIONS отдаёт ровно это (проверено скриптом
        # scripts/compare_mock_vs_public.py).
        del resp.headers["Content-Type"]
        resp.headers["Access-Control-Allow-Methods"] = "GET,HEAD,PUT,PATCH,POST,DELETE"
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Credentials"] = "true"
        resp.headers["Content-Length"] = "0"
        return resp
    return None


@app.errorhandler(404)
def not_found(_error) -> Response:
    """Неизвестный маршрут — 404 с телом ``{}`` (как у jsonplaceholder)."""
    return json_response({}, 404)


@app.errorhandler(405)
def method_not_allowed(_error) -> Response:
    """Метод, которого нет у маршрута.

    Публичный API на ``POST /users/1`` или ``PUT /users`` отвечает **404**
    с телом ``{}`` (json-server просто не находит подходящий маршрут), и
    только для ``TRACE`` отдаёт 405. Воспроизводим именно это.
    """
    if request.method in ("TRACE", "TRACK"):
        return json_response({}, 405)
    return json_response({}, 404)


def main() -> None:
    """Точка входа: запускает Flask-сервер на 127.0.0.1:8090."""
    port = int(os.environ.get("MOCK_PORT", DEFAULT_PORT))
    print("=" * 72)
    print("  Локальный мок jsonplaceholder.typicode.com")
    print(f"  Адрес:  http://127.0.0.1:{port}")
    print(f"  Данные: {DATA_FILE.name} ({len(USERS)} пользователей, снято с публичного API)")
    print("  Остановка: Ctrl+C")
    print("=" * 72)
    # threaded=True — чтобы параллельные запросы pytest не вставали в очередь.
    app.run(host="127.0.0.1", port=port, threaded=True, debug=False)


if __name__ == "__main__":
    main()
