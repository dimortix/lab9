/* Логика страницы входа. Учётные данные тестового стенда заданы в объекте USERS. */

const USERS = { admin: "admin123", student: "study2026" };

const form = document.getElementById("loginForm");
const username = document.getElementById("username");
const password = document.getElementById("password");
const remember = document.getElementById("remember");
const loginButton = document.getElementById("loginButton");
const welcomeBlock = document.getElementById("welcomeBlock");
const welcomeUser = document.getElementById("welcomeUser");
const logoutButton = document.getElementById("logoutButton");
const errors = {
  username: document.getElementById("usernameError"),
  password: document.getElementById("passwordError"),
  form: document.getElementById("formError"),
};

function showError(node, message) {
  node.textContent = message;
  node.hidden = false;
}

function clearErrors() {
  Object.values(errors).forEach((node) => {
    node.textContent = "";
    node.hidden = true;
  });
}

function login(user, pass) {
  clearErrors();
  let ok = true;

  if (!user.trim()) {
    showError(errors.username, "Введите логин");
    ok = false;
  }
  if (!pass) {
    showError(errors.password, "Введите пароль");
    ok = false;
  }
  if (!ok) return false;

  if (USERS[user] === undefined) {
    showError(errors.form, "Пользователь не найден");
    return false;
  }
  if (USERS[user] !== pass) {
    showError(errors.form, "Неверный пароль");
    return false;
  }

  // Успешный вход: форма скрывается, появляется блок приветствия с кнопкой Logout
  form.hidden = true;
  welcomeUser.textContent = user;
  welcomeBlock.hidden = false;
  sessionStorage.setItem("user", user);
  if (remember.checked) sessionStorage.setItem("remember", "1");
  return true;
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  login(username.value, password.value);
});

logoutButton.addEventListener("click", () => {
  sessionStorage.clear();
  welcomeBlock.hidden = true;
  form.hidden = false;
  username.value = "";
  password.value = "";
  clearErrors();
  username.focus();
});

// Если сессия уже открыта — показываем блок приветствия сразу
const savedUser = sessionStorage.getItem("user");
if (savedUser) {
  form.hidden = true;
  welcomeUser.textContent = savedUser;
  welcomeBlock.hidden = false;
}
