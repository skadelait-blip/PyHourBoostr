<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11%2B-blue?logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/Steam-ValvePython-green?logo=steam&logoColor=white" alt="Steam">
  <img src="https://img.shields.io/badge/GUI-PyQt6-purple?logo=qt&logoColor=white" alt="PyQt6">
  <img src="https://img.shields.io/badge/CLI-Colorama-yellow?logo=gnubash&logoColor=white" alt="CLI">
  <br>
  <img src="https://img.shields.io/github/license/skadelait-blip/PyHourBoostr" alt="License">
  <img src="https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey" alt="Platform">
  <img src="https://img.shields.io/badge/status-active-brightgreen" alt="Status">
</p>

---

# 🎮 PyHourBoostr

**Python-порт HourBoostr** — фармит игровые часы в Steam без установленного Steam-клиента.

Поддерживает несколько аккаунтов одновременно, SteamGuard (email + 2FA), login_key и работу на headless-серверах.

> 🧠 **Original idea & C# version:** [Ezzpify/HourBoostr](https://github.com/Ezzpify/HourBoostr)

---

## 📦 Установка

### Требования

- Python **3.11+**
- `pip`
- (Linux) `python3-venv`, `python3-dev`

---

### Windows

```powershell
# Клонируем репозиторий
git clone https://github.com/skadelait-blip/PyHourBoostr.git
cd PyHourBoostr

# Создаём виртуальное окружение
python -m venv venv
.\venv\Scripts\activate

# Ставим зависимости
pip install -r requirements.txt
```

### Linux / macOS

```bash
# Клонируем
git clone https://github.com/skadelait-blip/PyHourBoostr.git
cd PyHourBoostr

# Виртуальное окружение
python3 -m venv venv
source venv/bin/activate

# Зависимости
pip install -r requirements.txt

# На headless-сервере (без GUI) ставьте только CLI-зависимости:
pip install steam[client] colorama pycryptodomex
```

---

## 🚀 Запуск

### GUI (PyQt6) — только Windows

```powershell
python run_gui.py
```

### CLI — Windows / Linux / macOS

```bash
python main.py
```

Бот прочитает аккаунты из `Settings.json`, подключится к Steam и начнёт фармить часы.

---

## ⚙️ Настройка

Создайте `Settings.json` рядом с `main.py`:

```json
{
    "accounts": [
        {
            "details": {
                "username": "your_login",
                "password": "your_password",
                "login_key": ""
            },
            "games": [730]
        }
    ]
}
```

> 🔒 `Settings.json` добавлен в `.gitignore` — никогда не попадёт в репозиторий.

**Параметры аккаунта:**

| Поле | Описание |
|------|----------|
| `username` | Логин Steam |
| `password` | Пароль (будет автоматически очищен от пробелов) |
| `login_key` | Ключ для входа без пароля (заполняется автоматически после первого входа) |
| `games` | Список AppID игр (через запятую, макс. 32) |

**Глобальные настройки:**

| Поле | Описание |
|------|----------|
| `check_for_updates` | Проверять обновления при старте |
| `hide_to_tray` | Сворачивать в трей |

---

## 🛡️ SteamGuard / 2FA

- При запросе кода **email** — бот попросит ввести код из письма
- При запросе **2FA** (мобильный аутентификатор) — введите код из приложения Steam
- После успешного входа Steam выдаёт `login_key` — следующие входы будут без пароля
- Sentry-файлы хранятся в папке `Sentryfiles/` (игнорируется git)

---

## 📁 Структура проекта

```
.
├── bot.py              # Логика бота для одного аккаунта
├── steam_client.py     # Обёртка ValvePython SteamClient + фиксы
├── gui.py              # PyQt6 интерфейс
├── session.py          # CLI-менеджер сессий
├── config.py           # Модели данных
├── settings_manager.py # Чтение/запись Settings.json
├── endpoints.py        # Константы путей
├── logger.py           # Логирование
├── main.py             # Точка входа CLI
├── run_gui.py          # Точка входа GUI
├── requirements.txt    # Зависимости
├── Settings.json       # ⚠️ Аккаунты (не коммитить!)
├── Sentryfiles/        # Sentry-файлы Steam (не коммитить!)
└── Logs/               # Логи работы (не коммитить!)
```

---

## 🐍 Чем отличается от C# оригинала

| Оригинал (C#) | PyHourBoostr (Python) |
|---------------|----------------------|
| SteamKit2 | ValvePython `steam[client]` |
| Только Windows | Windows / Linux / macOS |
| .NET Framework | Python 3.11+ |
| GUI только WinForms | PyQt6 GUI + CLI |
| `login_key` не сохраняется | `login_key` сохраняется в Settings.json |
| Пробелы в пароле — ошибка | Пароль автоматически стриппится |

---

## 🧑‍💻 Авторы

- **Ezzpify** — оригинальная идея и [C# реализация](https://github.com/Ezzpify/HourBoostr)
- **3umukc** — Python-порт (ValvePython, PyQt6, фиксы совместимости)

---

## 📄 Лицензия

[MIT](LICENSE)
