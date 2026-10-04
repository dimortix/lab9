"""ЛР3: автотесты страницы логина (Selenium WebDriver + pytest).

Запуск:
    cd "/Users/dimortix/Личное/учеба/Тестирование по/lab3_selenium"
    ../.venv/bin/python -m pytest tests/test_login.py -v

Позитивный сценарий проверяет успешный вход по появлению элемента «Logout»,
негативные — тексты ошибок валидации и отказ при неверных учётных данных.
"""
import pytest
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


# Все тесты файла относятся к набору UI (см. маркеры в pytest.ini).
pytestmark = pytest.mark.ui

VALID = ("admin", "admin123")          # валидные учётные данные стенда
VALID_2 = ("student", "study2026")     # второй валидный пользователь
WAIT = 5


def login(driver, user: str, password: str, remember: bool = False) -> None:
    """Заполняет форму и нажимает «Войти»."""
    if user is not None:
        field = driver.find_element(By.ID, "username")
        field.clear()
        field.send_keys(user)
    if password is not None:
        field = driver.find_element(By.ID, "password")
        field.clear()
        field.send_keys(password)
    if remember:
        driver.find_element(By.ID, "remember").click()
    driver.find_element(By.ID, "loginButton").click()


def text_of_error(driver, error_id: str) -> str:
    """Возвращает текст видимого сообщения об ошибке."""
    element = WebDriverWait(driver, WAIT).until(
        EC.visibility_of_element_located((By.ID, error_id))
    )
    return element.text.strip()


# --------------------------- Позитивные сценарии ---------------------------

def test_stable_selectors_available_on_load(login_page):
    """Шаг 3 методички: на странице есть элементы со стабильными селекторами."""
    driver = login_page
    assert driver.find_element(By.ID, "username").is_displayed()
    assert driver.find_element(By.NAME, "password").is_displayed()
    assert driver.find_element(By.ID, "loginButton").is_enabled()
    assert driver.find_element(By.CSS_SELECTOR, "form#loginForm").is_displayed()
    assert driver.find_element(By.CSS_SELECTOR, "[data-testid='welcome']").is_displayed() is False


def test_successful_login_shows_logout(login_page, shots):
    """Автотест: валидные credentials → успешный вход (появляется «Logout»)."""
    driver = login_page
    login(driver, *VALID)

    logout = WebDriverWait(driver, WAIT).until(
        EC.visibility_of_element_located((By.ID, "logoutButton"))
    )
    assert logout.is_displayed(), "кнопка Logout не появилась после успешного входа"
    assert logout.text == "Logout"
    assert driver.find_element(By.ID, "welcomeUser").text == VALID[0]
    # Форма входа после успешного входа скрыта
    assert not driver.find_element(By.ID, "loginForm").is_displayed()
    driver.save_screenshot(str(shots / "ui_01_login_success.png"))


def test_successful_login_by_enter_key(login_page):
    """Вход по нажатию Enter в поле пароля работает так же, как клик по кнопке."""
    driver = login_page
    driver.find_element(By.ID, "username").send_keys(VALID_2[0])
    password = driver.find_element(By.ID, "password")
    password.send_keys(VALID_2[1])
    password.submit()

    logout = WebDriverWait(driver, WAIT).until(
        EC.visibility_of_element_located((By.ID, "logoutButton"))
    )
    assert logout.is_displayed()
    assert driver.find_element(By.ID, "welcomeUser").text == VALID_2[0]


def test_logout_returns_to_login_form(login_page):
    """После Logout снова показывается форма, поля очищены."""
    driver = login_page
    login(driver, *VALID)
    WebDriverWait(driver, WAIT).until(EC.element_to_be_clickable((By.ID, "logoutButton"))).click()

    form = WebDriverWait(driver, WAIT).until(EC.visibility_of_element_located((By.ID, "loginForm")))
    assert form.is_displayed()
    assert driver.find_element(By.ID, "username").get_attribute("value") == ""
    assert driver.find_element(By.ID, "password").get_attribute("value") == ""
    assert not driver.find_element(By.ID, "welcomeBlock").is_displayed()


def test_remember_me_stores_session_flag(login_page):
    """Чекбокс «Запомнить меня» сохраняет признак в sessionStorage."""
    driver = login_page
    login(driver, *VALID, remember=True)
    WebDriverWait(driver, WAIT).until(EC.visibility_of_element_located((By.ID, "logoutButton")))
    assert driver.execute_script("return sessionStorage.getItem('remember');") == "1"


# --------------------------- Негативные сценарии ---------------------------

def test_login_with_wrong_password(login_page, shots):
    """Неверный пароль: вход не выполнен, показана ошибка."""
    driver = login_page
    login(driver, VALID[0], "неверный-пароль")

    assert text_of_error(driver, "formError") == "Неверный пароль"
    assert not driver.find_element(By.ID, "logoutButton").is_displayed()
    driver.save_screenshot(str(shots / "ui_02_wrong_password.png"))


def test_login_with_unknown_user(login_page):
    """Несуществующий пользователь: отдельный текст ошибки."""
    driver = login_page
    login(driver, "nobody", "whatever")
    assert text_of_error(driver, "formError") == "Пользователь не найден"


def test_login_with_empty_fields(login_page, shots):
    """Пустые поля: валидация на клиенте, обе ошибки видны."""
    driver = login_page
    login(driver, "", "")
    assert text_of_error(driver, "usernameError") == "Введите логин"
    assert text_of_error(driver, "passwordError") == "Введите пароль"
    driver.save_screenshot(str(shots / "ui_03_empty_fields.png"))


def test_login_with_spaces_only_username(login_page):
    """Логин из пробелов считается пустым (trim)."""
    driver = login_page
    login(driver, "   ", VALID[1])
    assert text_of_error(driver, "usernameError") == "Введите логин"


@pytest.mark.parametrize(
    "user, password, expected_error",
    [
        ("admin", "Admin123", "Неверный пароль"),          # регистр пароля важен
        ("Admin", "admin123", "Пользователь не найден"),   # регистр логина важен
        ("admin", "admin123 ", "Неверный пароль"),         # пробел в конце пароля
        ("admin ", "admin123", "Пользователь не найден"),  # пробел в логине
    ],
)
def test_invalid_credentials_variants(login_page, user, password, expected_error):
    """Параметризация: разные варианты неверных данных не пускают в систему."""
    driver = login_page
    login(driver, user, password)
    assert text_of_error(driver, "formError") == expected_error
    assert not driver.find_element(By.ID, "welcomeBlock").is_displayed()


def test_error_is_cleared_on_next_attempt(login_page):
    """Сообщение об ошибке исчезает при следующей попытке входа."""
    driver = login_page
    login(driver, VALID[0], "плохой")
    assert text_of_error(driver, "formError") == "Неверный пароль"

    login(driver, *VALID)
    WebDriverWait(driver, WAIT).until(EC.visibility_of_element_located((By.ID, "logoutButton")))
    assert not driver.find_element(By.ID, "formError").is_displayed()


def test_password_field_masks_input(login_page):
    """Пароль не отображается открытым текстом (type=password)."""
    driver = login_page
    password = driver.find_element(By.ID, "password")
    assert password.get_attribute("type") == "password"
