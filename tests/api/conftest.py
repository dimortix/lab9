# -*- coding: utf-8 -*-
"""
Общие фикстуры и вспомогательные функции для тестов лабораторной работы №5.

Что здесь есть
--------------
1. ``base_url``      — адрес тестируемого API. Берётся из переменной окружения
                       ``API_BASE_URL``; по умолчанию — публичный
                       ``https://jsonplaceholder.typicode.com``.
2. ``api``           — готовая ``requests.Session`` с базовым адресом,
                       таймаутами, повторами для GET и сбором метрик.
3. ``mock_server``   — автоматически поднимает локальный мок (Flask) на
                       127.0.0.1:8090, если тесты запущены против него,
                       а он ещё не запущен. Это позволяет прогонять весь
                       набор тестов offline одной командой.
4. Помощники для проверки JSON-схем: ``assert_schema`` и словари-схемы
   ``USER_SCHEMA`` / ``USER_LIST_SCHEMA``. Пакет ``jsonschema`` в окружении
   курса не установлен, поэтому реализован компактный, но честный валидатор
   подмножества JSON Schema (type / required / properties / items / enum /
   pattern / minimum / additionalProperties).

Запуск против публичного API (по умолчанию)::

    pytest -v

Запуск против локального мока::

    API_BASE_URL=http://127.0.0.1:8090 pytest -v
"""

from __future__ import annotations

import os
import pathlib
import re
import socket
import subprocess
import sys
import time
from typing import Any

import pytest
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# --------------------------------------------------------------------------
# Константы
# --------------------------------------------------------------------------

#: Публичный API — объект тестирования по умолчанию.
PUBLIC_API_URL = "https://jsonplaceholder.typicode.com"

#: Адрес локального мока, повторяющего контракт публичного API.
MOCK_API_URL = "http://127.0.0.1:8090"

#: Таймаут одного HTTP-запроса (сек). Публичный API отвечает за 0.3-0.9 с,
#: поэтому 10 секунд — с большим запасом даже для медленной сети.
REQUEST_TIMEOUT = 10.0

#: Порог времени ответа для проверок производительности (сек).
#: Замеры публичного API: минимум 0.32 с, максимум 0.91 с — порог 3 с
#: оставляет запас и не даёт тесту «мигать» на медленном канале.
MAX_RESPONSE_TIME = 3.0

#: Корень репозитория (папка lab5_api).
ROOT_DIR = pathlib.Path(__file__).resolve().parent.parent

# --------------------------------------------------------------------------
# JSON-схемы тестируемого контракта
# --------------------------------------------------------------------------

#: Схема одного пользователя (контракт jsonplaceholder GET /users/{id}).
#:
#: Структура зафиксирована реальным запросом: плоский объект с двумя
#: вложенными объектами (address, company) и одним объектом третьего уровня
#: вложенности (address.geo).
USER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": [
        "id",
        "name",
        "username",
        "email",
        "address",
        "phone",
        "website",
        "company",
    ],
    "additionalProperties": False,
    "properties": {
        "id": {"type": "integer", "minimum": 1},
        "name": {"type": "string", "minLength": 1},
        "username": {"type": "string", "minLength": 1},
        "email": {"type": "string", "pattern": r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$"},
        "phone": {"type": "string", "minLength": 1},
        "website": {"type": "string", "minLength": 1},
        "address": {
            "type": "object",
            "required": ["street", "suite", "city", "zipcode", "geo"],
            "additionalProperties": False,
            "properties": {
                "street": {"type": "string"},
                "suite": {"type": "string"},
                "city": {"type": "string"},
                "zipcode": {"type": "string"},
                "geo": {
                    "type": "object",
                    "required": ["lat", "lng"],
                    "additionalProperties": False,
                    # Координаты публичный API отдаёт СТРОКАМИ, а не числами.
                    # Это зафиксировано и проверяется отдельным тестом.
                    "properties": {
                        "lat": {"type": "string"},
                        "lng": {"type": "string"},
                    },
                },
            },
        },
        "company": {
            "type": "object",
            "required": ["name", "catchPhrase", "bs"],
            "additionalProperties": False,
            "properties": {
                "name": {"type": "string"},
                "catchPhrase": {"type": "string"},
                "bs": {"type": "string"},
            },
        },
    },
}

#: Схема ответа GET /users — массив пользователей.
USER_LIST_SCHEMA: dict[str, Any] = {
    "type": "array",
    "minItems": 1,
    "items": USER_SCHEMA,
}

#: Схема тела 404-ответа публичного API — это ПУСТОЙ объект ``{}``.
#: Особенность зафиксирована реальными запросами (нет ни ``error``, ни
#: ``message``), поэтому она проверяется как часть контракта.
ERROR_404_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": [],
    "additionalProperties": False,
}


# --------------------------------------------------------------------------
# Мини-валидатор JSON Schema
# --------------------------------------------------------------------------


class SchemaValidationError(AssertionError):
    """Ошибка несоответствия JSON-схеме (наследник AssertionError для pytest)."""


_TYPE_MAP: dict[str, tuple[type, ...]] = {
    "object": (dict,),
    "array": (list,),
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
    "null": (type(None),),
}


def _type_name(value: Any) -> str:
    """Человекочитаемое имя типа значения для сообщений об ошибках."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def validate_schema(instance: Any, schema: dict[str, Any], path: str = "$") -> list[str]:
    """Проверяет значение ``instance`` на соответствие ``schema``.

    Поддерживаемое подмножество JSON Schema:
    ``type``, ``required``, ``properties``, ``additionalProperties``,
    ``items``, ``minItems``, ``enum``, ``pattern``, ``minimum``, ``minLength``.

    :return: список текстовых описаний найденных несоответствий
             (пустой список означает, что значение схеме соответствует).
    """
    errors: list[str] = []

    # --- type -------------------------------------------------------------
    expected_type = schema.get("type")
    if expected_type is not None:
        allowed = _TYPE_MAP[expected_type]
        # bool — подкласс int в Python, поэтому проверяем его отдельно,
        # иначе True прошёл бы проверку на "integer".
        is_bool_mismatch = isinstance(instance, bool) and expected_type != "boolean"
        if not isinstance(instance, allowed) or is_bool_mismatch:
            errors.append(
                f"{path}: ожидался тип '{expected_type}', "
                f"получено '{_type_name(instance)}'"
            )
            # Дальнейшие проверки для неверного типа бессмысленны.
            return errors

    # --- enum -------------------------------------------------------------
    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{path}: значение {instance!r} не входит в {schema['enum']!r}")

    # --- строковые ограничения -------------------------------------------
    if isinstance(instance, str):
        if "minLength" in schema and len(instance) < schema["minLength"]:
            errors.append(
                f"{path}: длина строки {len(instance)} < minLength="
                f"{schema['minLength']}"
            )
        if "pattern" in schema and not re.search(schema["pattern"], instance):
            errors.append(
                f"{path}: строка {instance!r} не соответствует шаблону "
                f"{schema['pattern']!r}"
            )

    # --- числовые ограничения --------------------------------------------
    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            errors.append(
                f"{path}: значение {instance} меньше minimum={schema['minimum']}"
            )

    # --- объект -----------------------------------------------------------
    if isinstance(instance, dict):
        for key in schema.get("required", []):
            if key not in instance:
                errors.append(f"{path}: отсутствует обязательное поле '{key}'")

        properties = schema.get("properties", {})
        for key, sub_schema in properties.items():
            if key in instance:
                errors.extend(
                    validate_schema(instance[key], sub_schema, f"{path}.{key}")
                )

        if schema.get("additionalProperties") is False:
            extra = sorted(set(instance) - set(properties))
            if extra:
                errors.append(f"{path}: неожиданные поля {extra}")

    # --- массив -----------------------------------------------------------
    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            errors.append(
                f"{path}: элементов {len(instance)} < minItems={schema['minItems']}"
            )
        items_schema = schema.get("items")
        if items_schema:
            for index, item in enumerate(instance):
                errors.extend(validate_schema(item, items_schema, f"{path}[{index}]"))

    return errors


def assert_schema(instance: Any, schema: dict[str, Any], path: str = "$") -> None:
    """Утверждение: значение соответствует схеме.

    При несоответствии падает с понятным многострочным сообщением, где
    перечислены все найденные расхождения (а не только первое).
    """
    errors = validate_schema(instance, schema, path)
    if errors:
        joined = "\n  - ".join(errors)
        raise SchemaValidationError(
            f"JSON не соответствует схеме ({len(errors)} расхождений):\n  - {joined}"
        )


def assert_json_response(response: requests.Response) -> Any:
    """Проверяет, что ответ — валидный JSON, и возвращает разобранное тело."""
    try:
        return response.json()
    except ValueError as exc:  # requests выбрасывает json.JSONDecodeError
        raise AssertionError(
            f"Ответ не является валидным JSON: {exc}\n"
            f"Тело (первые 300 символов): {response.text[:300]!r}"
        ) from exc


# --------------------------------------------------------------------------
# Фикстуры
# --------------------------------------------------------------------------


def _is_port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    """Проверяет, слушает ли кто-нибудь порт."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        return sock.connect_ex((host, port)) == 0


def _wait_for_server(url: str, timeout: float = 20.0) -> bool:
    """Ждёт, пока сервер начнёт отвечать на /health."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if requests.get(f"{url}/health", timeout=1.5).status_code == 200:
                return True
        except requests.RequestException:
            time.sleep(0.25)
    return False


@pytest.fixture(scope="session")
def base_url() -> str:
    """Базовый адрес тестируемого API.

    Значение берётся из переменной окружения ``API_BASE_URL``. Если переменная
    не задана, используется публичный jsonplaceholder — то есть обычный запуск
    ``pytest`` проверяет настоящий сервис в интернете.
    """
    url = os.environ.get("API_BASE_URL", PUBLIC_API_URL).strip()
    if not url:
        url = PUBLIC_API_URL
    return url.rstrip("/")


@pytest.fixture(scope="session")
def mock_server(base_url: str):
    """Поднимает локальный мок-сервер, если тесты запущены против него.

    Фикстура активируется только тогда, когда ``API_BASE_URL`` указывает на
    локальный адрес (127.0.0.1 / localhost). Если сервер уже запущен вручную
    (например, из другого терминала), он переиспользуется, а не запускается
    повторно. По завершении тестов автоматически запущенный процесс
    останавливается.
    """
    is_local = "127.0.0.1" in base_url or "localhost" in base_url
    if not is_local:
        # Тестируем публичный API — мок не нужен.
        yield None
        return

    host = "127.0.0.1"
    port = int(base_url.rsplit(":", 1)[-1].split("/")[0])

    if _is_port_open(host, port):
        # Сервер уже поднят (вручную или предыдущим запуском).
        yield None
        return

    if os.environ.get("AUTOSTART_MOCK", "1") != "1":
        pytest.fail(
            f"Мок-сервер не запущен на {base_url}, а AUTOSTART_MOCK=0. "
            "Запустите: python mock_server/app.py"
        )

    app_path = ROOT_DIR / "mock_server" / "app.py"
    env = {**os.environ, "MOCK_PORT": str(port)}
    process = subprocess.Popen(
        [sys.executable, str(app_path)],
        cwd=str(ROOT_DIR),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        if not _wait_for_server(base_url):
            process.terminate()
            pytest.fail(
                f"Не удалось запустить мок-сервер на {base_url} за 20 секунд"
            )
        yield process
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()


class ApiClient:
    """Тонкая обёртка над ``requests.Session`` с поддержкой относительных путей.

    Зачем нужна обёртка: ``requests`` требует абсолютный URL, поэтому писать
    в каждом тесте ``api.get(f"{base_url}/users/1")`` неудобно и легко
    ошибиться. Здесь достаточно ``api.get("/users/1")``.

    Дополнительно клиент запоминает время последнего ответа — это используется
    тестами производительности.
    """

    def __init__(self, session: requests.Session, base_url: str) -> None:
        self.session = session
        self.base_url = base_url.rstrip("/")
        self.last_elapsed: float = 0.0

    # -- служебное --------------------------------------------------------
    def url(self, path: str) -> str:
        """Склеивает базовый адрес и относительный путь."""
        if path.startswith(("http://", "https://")):
            return path
        return f"{self.base_url}/{path.lstrip('/')}"

    def request(self, method: str, path: str, **kwargs) -> requests.Response:
        """Выполняет запрос, подставляя базовый адрес и таймаут по умолчанию."""
        kwargs.setdefault("timeout", REQUEST_TIMEOUT)
        response = self.session.request(method, self.url(path), **kwargs)
        self.last_elapsed = response.elapsed.total_seconds()
        return response

    # -- HTTP-методы ------------------------------------------------------
    def get(self, path: str, **kwargs) -> requests.Response:
        """GET-запрос к API."""
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs) -> requests.Response:
        """POST-запрос к API."""
        return self.request("POST", path, **kwargs)

    def put(self, path: str, **kwargs) -> requests.Response:
        """PUT-запрос к API."""
        return self.request("PUT", path, **kwargs)

    def patch(self, path: str, **kwargs) -> requests.Response:
        """PATCH-запрос к API."""
        return self.request("PATCH", path, **kwargs)

    def delete(self, path: str, **kwargs) -> requests.Response:
        """DELETE-запрос к API."""
        return self.request("DELETE", path, **kwargs)

    def close(self) -> None:
        """Закрывает нижележащую сессию."""
        self.session.close()


@pytest.fixture(scope="session")
def api(base_url: str, mock_server) -> ApiClient:
    """Настроенный клиент API — основной инструмент тестов.

    * базовый адрес уже подставлен (в тестах пишем относительный путь);
    * заданы разумные таймауты;
    * для безопасных методов (GET/HEAD/OPTIONS) включены повторы при
      обрывах соединения — публичный API за Cloudflare иногда «моргает»;
      POST/PUT/DELETE намеренно НЕ повторяются, чтобы не создавать
      дубликаты записей;
    * заголовок ``User-Agent`` помогает отличить трафик лабораторной работы.
    """
    session = requests.Session()
    session.headers.update(
        {
            "Accept": "application/json",
            "User-Agent": "lab5-api-tests/1.0 (pytest; student Hvostenko D.B., 231-332)",
        }
    )

    retry = Retry(
        total=2,
        connect=2,
        read=0,
        backoff_factor=0.4,
        status_forcelist=(502, 503, 504),
        allowed_methods=frozenset(["GET", "HEAD", "OPTIONS"]),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    client = ApiClient(session, base_url)

    # --- проверка доступности -------------------------------------------
    try:
        probe = client.get("/users/1")
    except requests.RequestException as exc:
        client.close()
        pytest.exit(
            f"\n[ОШИБКА] API {base_url} недоступен: {exc}\n"
            "Проверьте интернет либо запустите локальный мок:\n"
            "  python mock_server/app.py\n"
            f"  API_BASE_URL={MOCK_API_URL} pytest -v\n",
            returncode=1,
        )
    if probe.status_code != 200:
        client.close()
        pytest.exit(
            f"\n[ОШИБКА] API {base_url} вернул {probe.status_code} на GET /users/1\n",
            returncode=1,
        )

    yield client
    client.close()


@pytest.fixture(scope="session")
def api_url(api: ApiClient) -> str:
    """Базовый адрес из уже проверенного клиента (для абсолютных URL)."""
    return api.base_url


@pytest.fixture
def assert_fast():
    """Фабрика проверок времени ответа.

    Использование::

        def test_x(api, assert_fast):
            response = api.get("/users/1")
            assert_fast(response)
    """

    def _check(response: requests.Response, limit: float = MAX_RESPONSE_TIME) -> None:
        elapsed = response.elapsed.total_seconds()
        assert elapsed < limit, (
            f"{response.request.method} {response.request.path_url} "
            f"выполнялся {elapsed:.3f} с, что больше порога {limit} с"
        )

    return _check


@pytest.fixture(scope="session")
def users_list(api: requests.Session) -> list[dict]:
    """Один раз за сессию получает коллекцию ``GET /users``.

    Нужен тестам, которые проверяют схему и уникальность id: 10 отдельных
    запросов вместо одного были бы лишней нагрузкой на публичный API.
    """
    response = api.get("/users", timeout=REQUEST_TIMEOUT)
    assert response.status_code == 200, (
        f"Подготовительный запрос GET /users вернул {response.status_code}"
    )
    return response.json()


@pytest.fixture
def unique_suffix() -> str:
    """Уникальный суффикс для данных создаваемого пользователя.

    Публичный jsonplaceholder не сохраняет записи, поэтому уникальность нужна
    только для читаемости отчёта и для проверки эха полей.
    """
    return f"{int(time.time() * 1000) % 1_000_000}"


@pytest.fixture
def created_user_payload(unique_suffix: str) -> dict:
    """Корректное тело запроса на создание пользователя (happy path)."""
    return {
        "name": f"Иван Петров {unique_suffix}",
        "username": f"ivan_{unique_suffix}",
        "email": f"ivan_{unique_suffix}@example.com",
        "phone": "+7-900-000-00-00",
        "website": "example.com",
    }
