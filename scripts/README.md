# Скрипты репозитория автотестов

## `run_ci_locally.sh`

Прогоняет **ровно тот же набор тестов**, что и workflow
`.github/workflows/run-tests.yml`, но локально — без push в GitHub.
Удобно, чтобы убедиться, что сборка будет зелёной.

```bash
bash scripts/run_ci_locally.sh
```

Скрипт последовательно выполняет три этапа (как три джобы CI):

1. `pytest tests/unit -m unit --cov=src` — модульные тесты с покрытием;
2. `pytest tests/api -m api` — тесты REST API (публичное API, а при отсутствии
   интернета — локальный мок `mock_server/app.py`);
3. `pytest tests/ui -m ui` — UI-тесты Selenium в headless-режиме.

Полный лог пишется в `../results/local_ci_run.txt`.
Код возврата: `0` — все наборы прошли, `1` — есть падения.
