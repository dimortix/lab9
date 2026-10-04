"""Фикстуры UI-тестов (Selenium) для CI-репозитория.

Отличия от локальной версии из ЛР3:
  * тестируемая страница логина лежит рядом, в каталоге app/ этого же репозитория;
  * ChromeDriver не «зашит» в путь: в CI его подбирает Selenium Manager,
    локально можно указать свой через переменную окружения CHROMEDRIVER;
  * headless-режим включается всегда (в CI нет дисплея).
"""
import os
from pathlib import Path

import pytest
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

REPO_ROOT = Path(__file__).resolve().parents[2]
LOGIN_URL = os.environ.get("LOGIN_URL") or (REPO_ROOT / "app" / "index.html").as_uri()
SHOTS_DIR = Path(__file__).resolve().parent / "screenshots"


def build_driver() -> webdriver.Chrome:
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--window-size=480,760")
    options.add_argument("--no-sandbox")             # обязательно в контейнерах CI
    options.add_argument("--disable-dev-shm-usage")  # /dev/shm в CI мал
    options.add_argument("--lang=ru-RU")

    driver_path = os.environ.get("CHROMEDRIVER")
    service = Service(driver_path) if driver_path and Path(driver_path).exists() else Service()
    return webdriver.Chrome(service=service, options=options)


@pytest.fixture()
def driver():
    browser = build_driver()
    yield browser
    browser.quit()


@pytest.fixture()
def login_page(driver):
    driver.get(LOGIN_URL)
    return driver


@pytest.fixture()
def shots():
    SHOTS_DIR.mkdir(exist_ok=True)
    return SHOTS_DIR
