# Автотесты (лабораторные работы №3, 4, 5, 6) и CI/CD через GitHub Actions

Репозиторий содержит код автотестов, разработанных в предыдущих лабораторных
работах, и настроенный пайплайн CI: тесты запускаются автоматически при каждом
push и pull request.

Дисциплина: «Тестирование программного обеспечения».
Выполнил: Хвостенко Д.Б., группа 231-332.

## Что внутри

| Каталог | Содержимое | Из какой лабораторной |
|---|---|---|
| `src/calculator.py` | класс `Calculator` — объект модульного тестирования | ЛР6 |
| `tests/unit/` | модульные тесты (pytest, параметризация, исключения) | ЛР6 |
| `tests/api/` | тесты REST API (`requests` + pytest, контрактные проверки) | ЛР5 |
| `tests/ui/` | UI-автотесты Selenium (страница логина, Page Object) | ЛР3, ЛР4 |
| `app/` | тестируемая страница логина (локальный стенд) | ЛР3 |
| `mock_server/` | локальный мок публичного API (на случай отсутствия сети) | ЛР5 |
| `.github/workflows/run-tests.yml` | конфигурация пайплайна GitHub Actions | ЛР9 |
| `scripts/run_ci_locally.sh` | локальный прогон того же набора тестов | ЛР9 |

## Как запускать тесты

### Локально (всё сразу)

```bash
bash scripts/run_ci_locally.sh
```

### Локально (по наборам)

```bash
pip install -r requirements-dev.txt

pytest tests/unit -m unit      # модульные тесты
pytest tests/api  -m api       # тесты REST API
pytest tests/ui   -m ui        # UI-тесты в headless Chrome
```

### Только модульные тесты с покрытием

```bash
pytest tests/unit -m unit --cov=src --cov-report=term-missing
```

## Пайплайн CI

Файл [`.github/workflows/run-tests.yml`](.github/workflows/run-tests.yml)
запускается при `push`, `pull_request` и вручную (`workflow_dispatch`) и состоит
из четырёх джоб:

1. **unit-tests** — матрица Python 3.11 и 3.12, прогон модульных тестов
   с отчётом о покрытии (артефакт `coverage.xml`);
2. **api-tests** — тесты REST API; перед прогоном проверяется доступность
   публичного API, и если сети нет, автоматически поднимается локальный мок;
3. **ui-tests** — UI-тесты Selenium в headless-режиме; скриншоты падений
   выгружаются артефактом;
4. **all-tests** — итоговая джоба: проходит только если все три набора
   тестов зелёные (единая «галочка» в интерфейсе GitHub).

Кэширование `pip` включено, зависимости зафиксированы в
`requirements-dev.txt`.

## Проверка пайплайна

Пайплайн проверен двумя способами:

1. **Локально** — `bash scripts/run_ci_locally.sh` выполняет те же команды,
   что и CI (лог: `../results/local_ci_run.txt`).
2. **В GitHub Actions** — реальные прогоны workflow в репозитории
   `dimortix/lab9` (вкладка Actions); в `../docs/ci_runs.md` приведены
   результаты прогонов, включая намеренно красный прогон.

## Ограничения

* UI-тесты требуют Chrome; в CI он есть на образах `ubuntu-latest`,
  локально используется установленный Chrome и ChromeDriver из
  `Selenium Manager` либо переменная окружения `CHROMEDRIVER`.
* Тесты API по умолчанию идут против публичного
  `https://jsonplaceholder.typicode.com`; поведение этого API зафиксировано
  в тестах (см. `../docs/analysis.md` в ЛР5), поэтому при изменении
  публичного сервиса часть тестов может «покраснеть» — это ожидаемо.
