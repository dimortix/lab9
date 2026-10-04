#!/usr/bin/env bash
# ===========================================================================
# Лабораторная работа №9. Локальный прогон ровно того же набора тестов,
# который запускает workflow .github/workflows/run-tests.yml.
# ---------------------------------------------------------------------------
# Зачем: GitHub Actions выполняет те же команды, но в облаке. Этот скрипт
# позволяет убедиться, что workflow пройдёт «зелёным», не делая push,
# и что локальное окружение совпадает с CI.
#
# Запуск:
#   bash scripts/run_ci_locally.sh
#
# Переменные окружения:
#   PYTHON — интерпретатор (по умолчанию — venv курса)
# ===========================================================================
set -uo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RESULTS_DIR="${REPO_DIR}/../results"
PYTHON="${PYTHON:-/Users/dimortix/Личное/учеба/Тестирование по/.venv/bin/python}"
LOG="${RESULTS_DIR}/local_ci_run.txt"

mkdir -p "${RESULTS_DIR}"
cd "${REPO_DIR}"

{
  echo "==============================================================="
  echo " Локальный прогон CI — $(date '+%Y-%m-%d %H:%M:%S %z')"
  echo "==============================================================="
  echo "Каталог репозитория: ${REPO_DIR}"
  echo "Интерпретатор:       ${PYTHON}"
  echo "Версия Python:       $("${PYTHON}" --version 2>&1)"
  echo "Chrome:              $(/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --version 2>/dev/null || echo 'не найден')"
  echo "pytest:              $("${PYTHON}" -m pytest --version 2>&1 | head -1)"
  echo
} | tee "${LOG}"

FAILED=0

run_stage() {
  local title="$1"; shift
  echo "" | tee -a "${LOG}"
  echo "---------------------------------------------------------------" | tee -a "${LOG}"
  echo " ЭТАП: ${title}" | tee -a "${LOG}"
  echo "---------------------------------------------------------------" | tee -a "${LOG}"
  "$@" 2>&1 | tee -a "${LOG}"
  local code=${PIPESTATUS[0]}
  echo "[${title}] код возврата: ${code}" | tee -a "${LOG}"
  [[ ${code} -ne 0 ]] && FAILED=1
  return 0
}

# --- Этап 1: модульные тесты (как джоба unit-tests) ------------------------
run_stage "unit-tests" "${PYTHON}" -m pytest tests/unit -m unit --cov=src --cov-report=term-missing

# --- Этап 2: тесты API (как джоба api-tests) -------------------------------
# Сначала публичное API, если недоступно — локальный мок (та же логика, что в CI).
if curl -sf --max-time 10 https://jsonplaceholder.typicode.com/users/1 > /dev/null; then
  echo "[api-tests] Публичное API доступно — тестируем его." | tee -a "${LOG}"
  run_stage "api-tests (публичное API)" "${PYTHON}" -m pytest tests/api -m api
else
  echo "[api-tests] Публичное API недоступно — поднимаю локальный мок." | tee -a "${LOG}"
  nohup "${PYTHON}" mock_server/app.py > "${RESULTS_DIR}/mock_server.log" 2>&1 &
  MOCK_PID=$!
  for _ in $(seq 1 30); do
    curl -sf http://127.0.0.1:8090/users/1 > /dev/null 2>&1 && break
    sleep 0.5
  done
  API_BASE_URL="http://127.0.0.1:8090" run_stage "api-tests (локальный мок)" "${PYTHON}" -m pytest tests/api -m api
  kill "${MOCK_PID}" 2>/dev/null || true
fi

# --- Этап 3: UI-тесты (как джоба ui-tests) ---------------------------------
# Локально используем ChromeDriver курса, если он есть; иначе Selenium Manager.
if [[ -x "/Users/dimortix/Личное/учеба/Тестирование по/tools/chromedriver-mac-arm64/chromedriver" ]]; then
  export CHROMEDRIVER="/Users/dimortix/Личное/учеба/Тестирование по/tools/chromedriver-mac-arm64/chromedriver"
fi
run_stage "ui-tests (Selenium, headless)" "${PYTHON}" -m pytest tests/ui -m ui

# --- Итог (как джоба all-tests) --------------------------------------------
echo "" | tee -a "${LOG}"
echo "===============================================================" | tee -a "${LOG}"
if [[ ${FAILED} -eq 0 ]]; then
  echo " ИТОГ: все наборы тестов прошли успешно (условная «зелёная галочка»)" | tee -a "${LOG}"
else
  echo " ИТОГ: есть упавшие тесты — сборка была бы красной" | tee -a "${LOG}"
fi
echo "===============================================================" | tee -a "${LOG}"
exit ${FAILED}
