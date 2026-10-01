#!/usr/bin/env python3
"""
thx for downloading!
"""

import argparse
import json
import os
import platform
import re
import shutil
import sys
import tempfile
import time
import traceback
import getpass  # Добавлено для безопасного ввода пароля

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    WebDriverException,
)

SHODAN_URL = "https://www.shodan.io/explore"
LOGIN_WAIT_SECONDS = 180
FIND_TIMEOUT = 8       # find timeout trying
FIND_POLL = 0.25       # DOM

CONFIG_FILE = "config.json" # Файл для сохранения почты и пароля

# -------------------------------------------------------------
# НАСТРОЙКИ: Базовые продукты и кодовое слово
# -------------------------------------------------------------
# Список базовых моделей (страна добавится динамически на основе выбора)
BASE_PRODUCTS = [
    'product:"Dahua IPC-C15"',
    'product:"Dahua IPC-A35"',
    'product:"Dahua IPC-K15"',
    'product:"Dahua IPC-K35"',
    'product:"Dahua IPC-K35A"',
    'product:"Dahua IPC-A15"',
    'product:"Dahua IPC-A26"',
    'product:"Dahua IPC-A46"',
    'product:"Dahua IPC-K26"',
    'product:"Dahua IPC-D26"',
    'product:"Dahua IPC-C46"'
]
TARGET_CODE_WORD = "Serial Number"
OUTPUT_FILE = "results.txt"  # Файл, куда будут сохраняться результаты
# -------------------------------------------------------------

# Глобальные переменные для учетных данных (заполняются в load_or_request_credentials)
GOOGLE_EMAIL = ""
GOOGLE_PASSWORD = ""

SKIP_DIRS = {
    "Cache", "Code Cache", "GPUCache", "Service Worker", "blob_storage",
    "IndexedDB", "Local Storage", "Session Storage", "Shared Dictionary",
    "GrShaderCache", "ShaderCache", "DawnCache", "commit_queue",
    "component_crx_cache", "Crashpad", "extensions_crx_cache",
    "Media Cache", "Application Cache", "File System", "Extensions",
    "Download Service", "OptimizationGuidePredictionModels",
}

VERBOSE = False
_T0 = time.time()


class C:
    OK = "\033[92m"
    INFO = "\033[96m"
    WARN = "\033[93m"
    ERR = "\033[91m"
    DIM = "\033[90m"
    BOLD = "\033[1m"
    END = "\033[0m"


def log(msg, kind="info"):
    color = {"ok": C.OK, "info": C.INFO, "warn": C.WARN, "err": C.ERR}.get(kind, C.INFO)
    prefix = {"ok": "[+]", "info": "[*]", "warn": "[!]", "err": "[x]"}.get(kind, "[*]")
    elapsed = f"{C.DIM}{time.time() - _T0:5.1f}s{C.END}"
    print(f"{elapsed} {color}{prefix} {msg}{C.END}")


def step(n, total, msg):
    bar = "─" * 44
    print(f"\n{C.BOLD}{bar}\n [{n}/{total}] {msg}\n{bar}{C.END}")


# ---------- Функция работы с конфигурацией (запоминание данных) ----------

def load_or_request_credentials():
    global GOOGLE_EMAIL, GOOGLE_PASSWORD
    
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                config = json.load(f)
                GOOGLE_EMAIL = config.get("email", "")
                GOOGLE_PASSWORD = config.get("password", "")
                if GOOGLE_EMAIL and GOOGLE_PASSWORD:
                    log("Учетные данные Google успешно загружены из сохраненного файла конфигурации.", "ok")
                    return
        except Exception as e:
            log(f"Не удалось прочитать файл конфигурации: {e}. Требуется ручной ввод.", "warn")

    print(f"\n{C.BOLD}{C.INFO}┌── Настройка учетных данных Google {C.END}")
    GOOGLE_EMAIL = input(f"{C.INFO}│{C.END} {C.BOLD}Введите ваш Email от Google:{C.END} ").strip()
    
    # Использование getpass маскирует ввод пароля в терминале (он пишется, но его не видно)
    GOOGLE_PASSWORD = getpass.getpass(f"{C.INFO}└──{C.END} {C.BOLD}Введите ваш Пароль от Google (ввод скрыт):{C.END} ").strip()
    
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump({"email": GOOGLE_EMAIL, "password": GOOGLE_PASSWORD}, f, ensure_ascii=False, indent=4)
        log(f"Учетные данные сохранены в файл '{CONFIG_FILE}' для последующих запусков.", "ok")
    except Exception as e:
        log(f"Не удалось сохранить конфигурацию: {e}", "err")


# ---------- выбор регионов ----------

def choose_regions() -> list:
    print(f"\n{C.BOLD}{C.INFO}┌── Выбор регионов для сканирования {C.END}")
    print(f"{C.INFO}│{C.END} Введите ISO-коды стран через запятую {C.DIM}(например: UA, US, PL, DE){C.END}")
    
    while True:
        user_input = input(f"{C.INFO}└──{C.END} {C.BOLD}Введите регионы{C.END} ➔ ").strip()
        
        if not user_input:
            print(f"{C.DIM}    {C.ERR}[x] Ошибка: Ввод пустой. Страна не обнаружена, проверьте.{C.END}")
            continue
        
        # Парсинг, очистка и фильтрация строго по 2 буквам (ISO-код)
        regions = []
        for item in user_input.split(","):
            cleaned = item.strip().upper().replace('"', '').replace("'", "")
            if len(cleaned) == 2 and cleaned.isalpha():
                regions.append(cleaned)
        
        # Если после фильтрации список пуст (ввели цифры, пробелы или длинные слова)
        if not regions:
            print(f"{C.DIM}    {C.ERR}[x] Ошибка: Валидные ISO-коды не найдены. Страна не обнаружена, проверьте.{C.END}")
            continue
            
        # Удаляем дубликаты, если одну страну написали дважды
        regions = list(dict.fromkeys(regions))
        
        # Если всё успешно, выходим из цикла
        countries_str = f"{C.BOLD}{C.OK}" + f"{C.END}, {C.BOLD}{C.OK}".join(regions) + f"{C.END}"
        print(f"{C.DIM}    Успешно установлены целевые зоны: [{countries_str}]{C.END}\n")
        return regions

import subprocess

def kill_chrome_zombies():
    """Мгновенно уничтожает все зомби-процессы ChromeDriver и автоматического Chrome
    с помощью быстрых системных утилит."""
    log("Выполняю мгновенную очистку памяти от процессов автоматизации...", "info")
    system = platform.system()
    
    try:
        if system == "Windows":
            # /F - принудительно, /T - дерево процессов, /IM - имя образа
            # Подавляем вывод в консоль через stdout/stderr, чтобы не засорять экран
            subprocess.run(["taskkill", "/F", "/T", "/IM", "chromedriver.exe"], 
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["taskkill", "/F", "/T", "/IM", "chrome.exe"], 
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            # На Linux / macOS используем быстрый pkill
            subprocess.run(["pkill", "-f", "chromedriver"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["pkill", "-f", "chrome"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        log("Память успешно очищена.", "ok")
    except Exception as e:
        log(f"Не удалось принудительно закрыть процессы: {e}", "warn")



# ---------- очистка повторных префиксов ----------

def remove_duplicate_prefixes():
    log("Запуск очистки дубликатов по префиксам серийных номеров...", "info")
    if not os.path.exists(OUTPUT_FILE):
        log(f"Файл {OUTPUT_FILE} не найден, очистка не требуется.", "warn")
        return

    try:
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()

        seen_prefixes = set()
        unique_lines = []

        # Регулярка теперь учитывает наличие временной метки в сохраненной строке
        pattern = rf"{re.escape(TARGET_CODE_WORD)}:\s*([A-Za-z0-9_\-]+)"

        for line in lines:
            match = re.search(pattern, line, re.IGNORECASE)
            if match:
                serial_value = match.group(1).strip()
                prefix = serial_value[:4].upper() 
                
                if prefix not in seen_prefixes:
                    seen_prefixes.add(prefix)
                    unique_lines.append(line)
            else:
                unique_lines.append(line)

        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.writelines(unique_lines)

        log(f"Очистка завершена. Удалено дубликатов префиксов: {len(lines) - len(unique_lines)}", "ok")

    except OSError as e:
        log(f"Не удалось обработать файл результатов при очистке: {e}", "err")


# ---------- профиль ----------

def default_user_data_dir() -> str:
    system = platform.system()
    home = os.path.expanduser("~")
    if system == "Windows":
        return os.path.join(os.environ.get("LOCALAPPDATA", home), "Google", "Chrome", "User Data")
    elif system == "Darwin":
        return os.path.join(home, "Library", "Application Support", "Google", "Chrome")
    else:
        return os.path.join(home, ".config", "google-chrome")


def list_profiles(user_data_dir: str):
    local_state_path = os.path.join(user_data_dir, "Local State")
    profiles = []
    if not os.path.isfile(local_state_path):
        return profiles
    try:
        with open(local_state_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        info_cache = data.get("profile", {}).get("info_cache", {})
        for dir_name, info in info_cache.items():
            profiles.append({
                "dir": dir_name,
                "name": info.get("name", dir_name),
                "email": info.get("user_name", "") or info.get("gaia_name", "") or "—",
            })
    except (json.JSONDecodeError, OSError) as e:
        log(f"Не удалось прочитать список профилей: {e}", "warn")
    return profiles


def choose_profile_interactively(profiles):
    print(f"\n{C.BOLD}Найденные профили Chrome:{C.END}")
    for i, p in enumerate(profiles, 1):
        print(f"  {i}. {p['name']}  ({p['email']})  [{p['dir']}]")
    print("  0. Ввести имя папки профиля вручную")

    while True:
        choice = input("\nВыберите профиль (номер): ").strip()
        if choice == "0":
            manual = input("Имя папки профиля (например 'Default' или 'Profile 1'): ").strip()
            return manual or "Default"
        if choice.isdigit() and 1 <= int(choice) <= len(profiles):
            return profiles[int(choice) - 1]["dir"]
        log("Некорректный ввод, попробуйте ещё раз.", "warn")


def resolve_profile(user_data_dir: str, profile_dir_arg):
    if profile_dir_arg:
        return profile_dir_arg
    profiles = list_profiles(user_data_dir)
    if not profiles:
        log("Не удалось автоматически найти профили, использую 'Default'.", "warn")
        return "Default"
    if len(profiles) == 1:
        log(f"Найден один профиль: {profiles[0]['name']} ({profiles[0]['email']})", "ok")
        return profiles[0]["dir"]
    return choose_profile_interactively(profiles)


def _safe_copy(src, dst):
    try:
        shutil.copy2(src, dst)
    except (OSError, PermissionError, shutil.Error):
        pass


def _ignore_heavy(dirpath, names):
    return [n for n in names if n in SKIP_DIRS]


def clone_profile(user_data_dir: str, profile_dir: str) -> str:
    tmp_root = tempfile.mkdtemp(prefix="chrome_clone_")
    log(f"Клонирую профиль во временную папку: {tmp_root}")

    local_state_src = os.path.join(user_data_dir, "Local State")
    if os.path.isfile(local_state_src):
        _safe_copy(local_state_src, os.path.join(tmp_root, "Local State"))

    src_profile = os.path.join(user_data_dir, profile_dir)
    dst_profile = os.path.join(tmp_root, profile_dir)
    if not os.path.isdir(src_profile):
        raise RuntimeError(f"Папка профиля не найдена: {src_profile}")

    shutil.copytree(
        src_profile, dst_profile,
        ignore=_ignore_heavy,
        copy_function=_safe_copy,
        dirs_exist_ok=True,
    )
    log("Профиль склонирован", "ok")
    return tmp_root


# ---------- драйвер ----------

def make_chrome_driver(user_data_dir: str, profile_dir: str):
    options = webdriver.ChromeOptions()
    options.add_argument("--window-size=800,600") 
    options.add_argument(f"--user-data-dir={user_data_dir}")
    options.add_argument(f"--profile-directory={profile_dir}")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
    options.add_experimental_option("useAutomationExtension", False)
    driver = webdriver.Chrome(options=options)
    try:
        driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"},
        )
    except WebDriverException:
        pass
    return driver


def get_driver(user_data_dir: str, profile_dir: str):
    log(f"Запускаю Chrome (клон профиля '{profile_dir}')...")
    try:
        driver = make_chrome_driver(user_data_dir, profile_dir)
        _ = driver.title
        log("Chrome запущен и под контролем", "ok")
        return driver
    except WebDriverException as e:
        detail = str(e).splitlines()[0] if str(e) else repr(e)
        if VERBOSE:
            traceback.print_exc()
        raise RuntimeError(
            f"Не удалось запустить управляемый Chrome.\nПричина: {detail}\n\n"
            "Частые причины:\n"
            "  - версия chromedriver не совпадает с версией Chrome\n"
            "  - антивирус/EDR блокирует автоматизацию Chrome\n"
            "  - недостаточно прав на запись во временную папку"
        ) from e


# ---------- быстрый поиск элементов ----------

def find_first(driver, selectors, timeout=FIND_TIMEOUT, poll=FIND_POLL, label=""):
    deadline = time.time() + timeout
    while time.time() < deadline:
        for by, sel in selectors:
            try:
                el = driver.find_element(by, sel)
                if el.is_displayed() and el.is_enabled():
                    return el
            except NoSuchElementException:
                continue
            except WebDriverException:
                continue
        time.sleep(poll)
    if label:
        log(f"Не нашёл '{label}' за {timeout} сек.", "warn")
    return None


def click(el, driver):
    try:
        el.click()
    except WebDriverException:
        driver.execute_script("arguments[0].click();", el)


# ---------- шаги флоу ----------

LOGIN_SELECTORS = [
    (By.LINK_TEXT, "Login"),
    (By.PARTIAL_LINK_TEXT, "Login"),
    (By.PARTIAL_LINK_TEXT, "Sign up"),
    (By.PARTIAL_LINK_TEXT, "Account"),
    (By.PARTIAL_LINK_TEXT, "Dashboard"),
    (By.CSS_SELECTOR, "a[href*='/login']"),
    (By.CSS_SELECTOR, "a[href*='/register']"),
    (By.CSS_SELECTOR, "a[href*='/account']"),
    (By.CSS_SELECTOR, "a[href*='/dashboard']"),
]

GOOGLE_SELECTORS = [
    (By.PARTIAL_LINK_TEXT, "Google"),
    (By.CSS_SELECTOR, "a[href*='google']"),
    (By.XPATH, "//button[contains(., 'Google')]"),
    (By.XPATH, "//*[contains(text(),'Continue with Google')]"),
]

EMAIL_INPUT_SELECTORS = [
    (By.CSS_SELECTOR, "input[type='email']"),
    (By.ID, "identifierId"),
    (By.NAME, "identifier")
]

PASSWORD_INPUT_SELECTORS = [
    (By.CSS_SELECTOR, "input[type='password']"),
    (By.NAME, "password")
]

NEXT_BUTTON_SELECTORS = [
    (By.ID, "identifierNext"),
    (By.ID, "passwordNext"),
    (By.XPATH, "//span[contains(text(), 'Далее')]/.."),
    (By.XPATH, "//span[contains(text(), 'Next')]/.."),
    (By.XPATH, "//button[contains(., 'Далее')]"),
    (By.XPATH, "//button[contains(., 'Next')]")
]

# Обновлено: Селектор аккаунта генерируется динамически в функции pick_google_account

SEARCH_SELECTORS = [
    (By.NAME, "query"),
    (By.CSS_SELECTOR, "input[type='search']"),
    (By.CSS_SELECTOR, "input#search"),
    (By.CSS_SELECTOR, "input.search-query"),
]


def open_shodan(driver):
    log(f"Загружаю {SHODAN_URL} ...")
    driver.get(SHODAN_URL)
    try:
        WebDriverWait(driver, 10).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
    except TimeoutException:
        log("Страница долго грузится, продолжаю всё равно.", "warn")
    log(f"Страница загружена: {driver.title!r}", "ok")


def click_login(driver) -> bool:
    el = find_first(driver, LOGIN_SELECTORS, label="кнопка Login/Account")
    if el is None:
        return False
    click(el, driver)
    log("Кликнул на Login/Account", "ok")
    return True


def click_google(driver) -> bool:
    el = find_first(driver, GOOGLE_SELECTORS, label="кнопка Continue with Google")
    if el is None:
        return False
    click(el, driver)
    log("Кликнул на 'Continue with Google'", "ok")
    return True


def pick_google_account(driver) -> bool:
    time.sleep(1)
    if "accounts.google" not in driver.current_url:
        return False

    email_input = find_first(driver, EMAIL_INPUT_SELECTORS, timeout=5, label="поле ввода Email")
    if email_input:
        log("Ввожу Email...")
        email_input.clear()
        email_input.send_keys(GOOGLE_EMAIL)
        
        next_btn = find_first(driver, NEXT_BUTTON_SELECTORS, timeout=3, label="кнопка Далее (Email)")
        if next_btn:
            click(next_btn, driver)
            time.sleep(1.5)
    else:
        dynamic_account_selectors = [
            (By.CSS_SELECTOR, f"div[data-identifier='{GOOGLE_EMAIL}']"),
            (By.CSS_SELECTOR, "div[data-identifier]"),
            (By.CSS_SELECTOR, "li[data-identifier]"),
            (By.XPATH, "//div[@data-authuser]"),
        ]
        account_el = find_first(driver, dynamic_account_selectors, timeout=3, label="аккаунт в списке")
        if account_el:
            click(account_el, driver)
            time.sleep(1.5)

    password_input = find_first(driver, PASSWORD_INPUT_SELECTORS, timeout=7, label="поле ввода Пароля")
    if password_input:
        log("Ввожу Пароль...")
        password_input.clear()
        password_input.send_keys(GOOGLE_PASSWORD)
        
        next_btn = find_first(driver, NEXT_BUTTON_SELECTORS, timeout=3, label="кнопка Далее (Пароль)")
        if next_btn:
            click(next_btn, driver)
            log("Данные отправлены. Ожидаю завершения авторизации...", "ok")
            return True
            
    return False


def wait_back_on_shodan(driver, timeout=LOGIN_WAIT_SECONDS):
    log(f"Жду возврата на shodan.io (до {timeout} сек)...")
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if "shodan.io" in driver.current_url and "accounts.google" not in driver.current_url:
                time.sleep(1)
                return True
        except WebDriverException:
            pass
        time.sleep(1)
    log("Время ожидания истекло, продолжаю в текущем состоянии.", "warn")
    return False

from datetime import datetime

def save_to_file(query_item, timestamp_value, result_value):
    try:
        # Приводим к строке и очищаем от пробелов
        ts_str = str(timestamp_value).strip() if timestamp_value else ""
        
        # Проверяем, что дата вообще есть и она валидна (исправление проверки)
        if ts_str and ts_str not in ["None", "0", "null", "false"]:
            try:
                #we are delete T to space and filter it for ONLY DAY / MONTH / YEAR
                date_part = ts_str.replace("T", " ").split(" ")[0]
                
                #today - days_ago
                #and we get how old are serial shodan update
                parsed_date = datetime.strptime(date_part, "%Y-%m-%d").date()
                today = datetime.now().date()
                days_ago = (today - parsed_date).days
                
                #formartt
                if days_ago == 0:
                    age_status = "сегодня"
                elif days_ago == 1:
                    age_status = "вчера"
                else:
                    age_status = f"{days_ago} дн. назад"
                
                
                # Записываем в файл строку с датой и расчетом возраста
                log_string = f"{query_item} [Дата: {date_part} | Возраст: {age_status}] -> {TARGET_CODE_WORD}: {result_value}\n"
                
            except Exception as parse_err:
                # Резервный вариант: если формат даты сломался, просто пишем сырой текст, чтобы не потерять серийник
                log_string = f"{query_item} [{ts_str}] -> {TARGET_CODE_WORD}: {result_value}\n"
        else:
            # Если даты не было изначально
            log_string = f"{query_item} -> {TARGET_CODE_WORD}: {result_value}\n"
            
        # Запись в файл
        with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
            f.write(log_string)
            
    except OSError as e:
        log(f"Не удалось записать результат в файл: {e}", "err")



def process_search_loop(driver, search_items):
    """
    Последовательно выполняет поиск, извлекает временную метку (timestamp) устройства
    и кодовое слово (Serial Number).
    """
    for idx, item in enumerate(search_items, 1):
        log(f"Начинаю обработку элемента [{idx}/{len(search_items)}]: '{item}'")
        
        if "shodan.io" not in driver.current_url:
            driver.get(SHODAN_URL)
            time.sleep(1)
            
        el = find_first(driver, SEARCH_SELECTORS, label=f"поле поиска для '{item}'")
        if el is None:
            log(f"Не удалось найти поисковую строку для элемента '{item}', пропускаю.", "err")
            continue
            
        click(el, driver)
        el.clear()
        el.send_keys(item)
        el.submit()
        log(f"Отправил поисковый запрос: '{item}'", "ok")
        
        time.sleep(1)
        
        try:
            page_content = driver.page_source
            
            # Находим все блоки с классом result
            result_blocks = re.findall(r'<div class="result">.*?</div>\s*</div>\s*</div>', page_content, re.DOTALL)
            
            if result_blocks:
                for block in result_blocks:
                    # Извлекаем timestamp
                    time_match = re.search(r'class="timestamp[^"]*">([^<]+)</div>', block, re.IGNORECASE)
                    timestamp = time_match.group(1).strip() if time_match else None
                    
                    # Извлекаем серийный номер
                    serial_match = re.search(rf"{re.escape(TARGET_CODE_WORD)}\s*:\s*([A-Za-z0-9_\-]+)", block, re.IGNORECASE)
                    if serial_match:
                        raw_value = str(serial_match.group(1)).strip()
                        truncated_value = raw_value[:10]
                        log(f"РЕЗУЛЬТАТ ДЛЯ '{item}' [{timestamp}] -> {TARGET_CODE_WORD}: {truncated_value}", "ok")
                        save_to_file(item, timestamp, truncated_value)
            else:
                # Способ 2 (резервный): Если блоки разметки не поддались регулярке, парсим через DOM элементы
                results = driver.find_elements(By.CLASS_NAME, "result")
                if not results:
                    log(f"На странице результатов для '{item}' ничего не найдено.", "warn")
                    continue
                
                for res_el in results:
                    try:
                        ts_el = res_el.find_element(By.CLASS_NAME, "timestamp")
                        timestamp = ts_el.text.strip()
                    except NoSuchElementException:
                        timestamp = None
                        
                    text = res_el.text
                    if TARGET_CODE_WORD.lower() in text.lower():
                        match = re.search(rf"{re.escape(TARGET_CODE_WORD)}\s*:\s*([A-Za-z0-9_\-]+)", text, re.IGNORECASE)
                        if match:
                            raw_value = str(match.group(1)).strip()
                            truncated_value = raw_value[:10]
                            log(f"РЕЗУЛЬТАТ (резервный) ДЛЯ '{item}' [{timestamp}] -> {TARGET_CODE_WORD}: {truncated_value}", "ok")
                            save_to_file(item, timestamp, truncated_value)
                
        except Exception as e:
            log(f"Ошибка при парсинге страницы для '{item}': {e}", "err")
            if VERBOSE:
                traceback.print_exc()
            
        time.sleep(1)


def main():
    global VERBOSE
    parser = argparse.ArgumentParser(description="Автоматизация Shodan c парсингом списков слов")
    parser.add_argument("--user-data-dir", default=None)
    parser.add_argument("--profile-dir", default=None)
    parser.add_argument("--verbose", action="store_true", help="Показывать полный traceback при ошибках")
    args = parser.parse_args()
    VERBOSE = args.verbose

    # Запрашиваем или считываем сохраненные почту и пароль
    load_or_request_credentials()

    selected_regions = choose_regions()
    log(f"Выбранные регионы: {', '.join(selected_regions)}", "ok")
    
    search_items = []
    for product in BASE_PRODUCTS:
        for region in selected_regions:
            search_items.append(f'{product} country:"{region}"')

    total_steps = 7
    user_data_dir = args.user_data_dir or default_user_data_dir()

    step(1, total_steps, "Определяю профиль Chrome")
    profile_dir = resolve_profile(user_data_dir, args.profile_dir)

    step(2, total_steps, "Клонирую профиль")
    try:
        clone_dir = clone_profile(user_data_dir, profile_dir)
    except (RuntimeError, OSError) as e:
        log(str(e), "err")
        sys.exit(1)

    step(3, total_steps, "Запускаю Chrome")
    try:
        driver = get_driver(clone_dir, profile_dir)
    except RuntimeError as e:
        log(str(e), "err")
        sys.exit(1)

    try:
        step(4, total_steps, "Открываю Shodan")
        open_shodan(driver)

        step(5, total_steps, "Ищу и жму Login/Account -> Continue with Google")
        if not click_login(driver):
            log("Кнопку логина не нашёл — жду, вдруг вы кликнете сами...", "warn")
        time.sleep(1)
        if not click_google(driver):
            log("Кнопку Google не нашёл — жду, вдруг вы кликнете сами...", "warn")

        step(6, total_steps, "Логинюсь через Google")
        pick_google_account(driver)
        wait_back_on_shodan(driver)

        step(7, total_steps, "Запуск цикла поиска по списку")
        process_search_loop(driver, search_items)

        remove_duplicate_prefixes()
        print(f"\n{C.OK}{C.BOLD}Все элементы из списка обработаны ({time.time() - _T0:.1f}s).{C.END} Окно браузера остаётся открытым.")
        print("Закройте его вручную, когда закончите (Ctrl+C для выхода из скрипта).")
        while True:
            time.sleep(5)
            
    except KeyboardInterrupt:
        log("Остановлено пользователем.")
    except Exception as e:
        log(f"Неожиданная ошибка: {e}", "err")
        if VERBOSE:
            traceback.print_exc()
            
    finally:
        # Сразу жестко чистим систему без долгих ожиданий драйвера
        kill_chrome_zombies()
        # Быстрый выход из Python, чтобы не висели другие потоки
        os._exit(0) 



if __name__ == "__main__":
    main()
