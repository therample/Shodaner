#!/usr/bin/env python3
"""
thx for downloading!
"""
from random import uniform
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
FIND_TIMEOUT = 5       # было 8
FIND_POLL = 0.1        # было 0.25

CONFIG_FILE = "config.json" # Файл для сохранения почты и пароля

# -------------------------------------------------------------
# НАСТРОЙКИ: Базовые продукты и кодовое слово
# -------------------------------------------------------------
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


# ---------- Функция работы с конфигурацией ----------

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
        
        regions = []
        for item in user_input.split(","):
            cleaned = item.strip().upper().replace('"', '').replace("'", "")
            if len(cleaned) == 2 and cleaned.isalpha():
                regions.append(cleaned)
        
        if not regions:
            print(f"{C.DIM}    {C.ERR}[x] Ошибка: Валидные ISO-коды не найдены. Страна не обнаружена, проверьте.{C.END}")
            continue
            
        regions = list(dict.fromkeys(regions))
        
        countries_str = f"{C.BOLD}{C.OK}" + f"{C.END}, {C.BOLD}{C.OK}".join(regions) + f"{C.END}"
        print(f"{C.DIM}    Успешно установлены целевые зоны: [{countries_str}]{C.END}\n")
        return regions

import subprocess

def kill_chrome_zombies():
    """Мгновенно уничтожает все зомби-процессы ChromeDriver и автоматического Chrome."""
    log("Выполняю мгновенную очистку памяти от процессов автоматизации...", "info")
    system = platform.system()
    
    try:
        if system == "Windows":
            subprocess.run(["taskkill", "/F", "/T", "/IM", "chromedriver.exe"], 
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["taskkill", "/F", "/T", "/IM", "chrome.exe"], 
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
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

    # === Безопасные флаги скорости (профиль не трогают) ===
    options.add_argument("--disable-background-networking")
    options.add_argument("--disable-background-timer-throttling")
    options.add_argument("--disable-backgrounding-occluded-windows")
    options.add_argument("--disable-renderer-backgrounding")
    options.add_argument("--disable-hang-monitor")
    options.add_argument("--disable-sync")
    options.add_argument("--disable-translate")
    options.add_argument("--mute-audio")

    # Не ждать картинки/шрифты — работать сразу после DOM
    options.page_load_strategy = "eager"

    options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
    options.add_experimental_option("useAutomationExtension", False)

    # Отключаем картинки (серийники — в тексте, картинки не нужны)
    options.add_experimental_option("prefs", {
        "profile.managed_default_content_settings.images": 2,
        "profile.default_content_setting_values.notifications": 2,
    })

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
            lambda d: d.execute_script("return document.readyState") in ("complete", "interactive")
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
    time.sleep(0.5)
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
            time.sleep(0.8)
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
            time.sleep(0.8)

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
                time.sleep(0.5)
                return True
        except WebDriverException:
            pass
        time.sleep(0.5)
    log("Время ожидания истекло, продолжаю в текущем состоянии.", "warn")
    return False

from datetime import datetime


# ---------- детекция и авто-решение капчи Cloudflare ----------

# ---------- детекция и авто-решение капчи Cloudflare ----------

CLOUDFLARE_MARKERS = [
    "performing security verification",
    "just a moment",
    "checking your browser before accessing",
    "verifying you are human",
    "cf-challenge",
    "cf_chl_opt",
    "challenge-platform",
    "this website uses a security service to protect against malicious bots",
]


def is_cloudflare_challenge(driver) -> bool:
    try:
        title = (driver.title or "").lower()
        if "just a moment" in title or "attention required" in title:
            return True
        src = (driver.page_source or "").lower()
        for marker in CLOUDFLARE_MARKERS:
            if marker in src:
                return True
    except WebDriverException:
        pass
    return False


# JS: ищет в DOM (включая ОТКРЫТЫЕ shadow roots):
#   1) Turnstile iframe;
#   2) чекбокс "Verify you are human" — input[type=checkbox] или [role=checkbox].
# ВНИМАНИЕ: закрытый shadow DOM этим не пробивается — для него есть CDP-клик.
_TURNSTILE_FIND_JS = r"""
function deepFind(root, match) {
  let all;
  try { all = root.querySelectorAll('*'); } catch (e) { return null; }
  for (const el of all) {
    try { if (match(el)) return el; } catch (e) {}
  }
  for (const el of all) {
    if (el.shadowRoot) {
      const found = deepFind(el.shadowRoot, match);
      if (found) return found;
    }
  }
  return null;
}

// 1) Turnstile-iframe
const iframeEl = deepFind(document, (el) => {
  if (el.tagName !== 'IFRAME') return false;
  const src = (el.src || '').toLowerCase();
  const title = (el.getAttribute('title') || '').toLowerCase();
  return src.includes('challenges.cloudflare.com') ||
         src.includes('turnstile') ||
         title.includes('cloudflare');
});
if (iframeEl) return iframeEl;

// 2) Чекбокс (input или role=checkbox)
const cbEl = deepFind(document, (el) => {
  const tag = el.tagName.toLowerCase();
  const type = (el.type || '').toLowerCase();
  const role = (el.getAttribute('role') || '').toLowerCase();
  const aria = (el.getAttribute('aria-label') || '').toLowerCase();

  if (tag === 'input' && type === 'checkbox') {
    const rect = el.getBoundingClientRect();
    if (rect.width > 0 && rect.height > 0) {
      if (aria.includes('human') || aria.includes('verify')) return true;
      let p = el.parentElement;
      for (let i = 0; i < 8 && p; i++) {
        if ((p.textContent || '').toLowerCase().includes('verify you are human')) return true;
        p = p.parentElement;
      }
    }
    return false;
  }

  if (role === 'checkbox') {
    const rect = el.getBoundingClientRect();
    if (rect.width > 0 && rect.height > 0) {
      if (aria.includes('human') || aria.includes('verify')) return true;
      let p = el.parentElement;
      for (let i = 0; i < 6 && p; i++) {
        if ((p.textContent || '').toLowerCase().includes('verify you are human')) return true;
        p = p.parentElement;
      }
    }
  }
  return false;
});
return cbEl;
"""


# JS-диагностика: что видно на странице сейчас
_TURNSTILE_DIAG_JS = r"""
function countShadow(root) {
  let n = 0;
  try {
    const all = root.querySelectorAll('*');
    for (const el of all) {
      if (el.shadowRoot) { n++; n += countShadow(el.shadowRoot); }
    }
  } catch (e) {}
  return n;
}
function countDeep(root, sel) {
  let n = 0;
  try {
    n += root.querySelectorAll(sel).length;
    const all = root.querySelectorAll('*');
    for (const el of all) {
      if (el.shadowRoot) n += countDeep(el.shadowRoot, sel);
    }
  } catch (e) {}
  return n;
}
var bc = document.querySelector('#bcQj6');
var bcInfo = null;
if (bc) {
  var r = bc.getBoundingClientRect();
  bcInfo = {
    children: bc.children.length,
    html_len: (bc.outerHTML || '').length,
    w: Math.round(r.width),
    h: Math.round(r.height),
  };
}
return {
  iframes_deep: countDeep(document, 'iframe'),
  checkboxes_deep: countDeep(document, 'input[type=checkbox]'),
  role_checkbox_deep: countDeep(document, '[role=checkbox]'),
  shadow_roots: countShadow(document),
  bcQj6: bcInfo,
  ready_state: document.readyState,
};
"""


def _find_turnstile_element(driver):
    try:
        return driver.execute_script(_TURNSTILE_FIND_JS)
    except WebDriverException:
        return None


def _diag_turnstile(driver):
    try:
        return driver.execute_script(_TURNSTILE_DIAG_JS) or {}
    except WebDriverException:
        return {}


def _click_checkbox_via_selenium(driver, cb) -> bool:
    try:
        cb.click()
        return True
    except WebDriverException:
        pass
    try:
        driver.execute_script(
            "arguments[0].scrollIntoView({block:'center'});"
            "arguments[0].click();",
            cb,
        )
        return True
    except WebDriverException:
        pass
    try:
        driver.execute_script(
            "var el = arguments[0];"
            "while (el && el.tagName !== 'LABEL') el = el.parentElement;"
            "if (el) el.click();",
            cb,
        )
        return True
    except WebDriverException:
        pass
    return False


def _click_at_cdp(driver, x: float, y: float) -> bool:
    """Реальный клик мышью через CDP по viewport-координатам."""
    try:
        driver.execute_cdp_cmd("Input.dispatchMouseEvent", {
            "type": "mouseMoved", "x": x, "y": y,
        })
        driver.execute_cdp_cmd("Input.dispatchMouseEvent", {
            "type": "mousePressed", "x": x, "y": y,
            "button": "left", "clickCount": 1,
        })
        driver.execute_cdp_cmd("Input.dispatchMouseEvent", {
            "type": "mouseReleased", "x": x, "y": y,
            "button": "left", "clickCount": 1,
        })
        return True
    except WebDriverException:
        return False


def _click_widget_by_coords(driver, element) -> bool:
    """
    Клик по координатам внутри элемента — для случая ЗАКРЫТОГО shadow DOM,
    когда чекбокс виден визуально, но недоступен для Selenium/JS.
    """
    try:
        driver.execute_script(
            "arguments[0].scrollIntoView({block:'center'});", element
        )
        time.sleep(0.3)
        # getBoundingClientRect() возвращает viewport-координаты —
        # именно их ждёт CDP Input.dispatchMouseEvent.
        rect = driver.execute_script(
            "var r = arguments[0].getBoundingClientRect();"
            "return {x: r.x, y: r.y, width: r.width, height: r.height};",
            element,
        )
    except WebDriverException:
        return False

    if not rect:
        return False
    w = rect.get("width") or 0
    h = rect.get("height") or 0
    if w <= 1 or h <= 1:
        return False

    # Пробуем: левый край (там обычно чекбокс), центр, чуть выше центра.
    points = [
        (rect["x"] + min(20, w * 0.15), rect["y"] + h / 2),
        (rect["x"] + w / 2,             rect["y"] + h / 2),
        (rect["x"] + w * 0.5,           rect["y"] + h * 0.35),
    ]
    for x, y in points:
        if _click_at_cdp(driver, x, y):
            return True
    return False


def _solve_via_iframe(driver, iframe_el) -> bool:
    """Переключается в iframe и кликает чекбокс. True если клик прошёл."""
    ready_cb = None
    try:
        driver.switch_to.frame(iframe_el)
        deadline = time.time() + 30
        while time.time() < deadline:
            try:
                cbs = driver.find_elements(By.CSS_SELECTOR, "input[type='checkbox']")
            except WebDriverException:
                cbs = []
            if not cbs:
                time.sleep(0.3)
                continue
            cb = cbs[0]
            try:
                if not cb.is_displayed() or not cb.is_enabled():
                    time.sleep(0.3)
                    continue
            except WebDriverException:
                time.sleep(0.3)
                continue
            verifying = False
            try:
                for el in driver.find_elements(By.XPATH, "//*[contains(text(), 'Verifying')]"):
                    if el.is_displayed():
                        verifying = True
                        break
            except WebDriverException:
                pass
            if verifying:
                time.sleep(0.3)
                continue
            ready_cb = cb
            break
        if ready_cb is not None:
            if _click_checkbox_via_selenium(driver, ready_cb):
                log("Кликнул по чекбоксу (внутри iframe).", "ok")
                return True
    except WebDriverException:
        pass
    finally:
        try:
            driver.switch_to.default_content()
        except WebDriverException:
            pass
    return False


def auto_solve_cloudflare_checkbox(driver, timeout=90) -> bool:
    """
    Пытается автоматически пройти Cloudflare Turnstile. Порядок попыток:
      1) JS-поиск iframe / чекбокса (включая ОТКРЫТЫЕ shadow roots);
      2) Selenium-поиск input[type=checkbox] на случай, если JS-диагностика
         что-то упустила;
      3) Реальный клик мышью по координатам #bcQj6 — для случая ЗАКРЫТОГО
         shadow DOM, когда чекбокс виден визуально, но не в DOM.
    """
    log("Обнаружена защита Cloudflare. Пробую решить автоматически...", "info")
    start = time.time()
    last_log = 0.0
    last_click_at = 0.0
    clicked_count = 0
    bc_first_seen = None
    max_clicks = 20

    while time.time() - start < timeout:
        if not is_cloudflare_challenge(driver):
            log(f"Cloudflare пройден за {time.time() - start:.1f}s (кликов: {clicked_count}).", "ok")
            return True

        # --- 1) JS-поиск (iframe / input / role=checkbox) ---
        el = _find_turnstile_element(driver)
        if el is not None and clicked_count < max_clicks:
            try:
                tag = (el.tag_name or "").lower()
            except WebDriverException:
                tag = ""

            if tag == "iframe":
                log("Нашёл Turnstile-iframe.", "ok")
                if _solve_via_iframe(driver, el):
                    clicked_count += 1
                    last_click_at = time.time()
                time.sleep(0.5)
                continue
            elif tag in ("input", "div", "button", "span"):
                log(f"Нашёл элемент чекбокса ({tag}).", "ok")
                if _click_checkbox_via_selenium(driver, el):
                    clicked_count += 1
                    last_click_at = time.time()
                time.sleep(0.5)
                continue

        # --- 2) Selenium-fallback ---
        clicked_this_round = False
        if clicked_count < max_clicks:
            try:
                sel_cbs = driver.find_elements(By.CSS_SELECTOR, "input[type=checkbox]")
            except WebDriverException:
                sel_cbs = []
            for cb in sel_cbs:
                try:
                    if cb.is_displayed() and cb.is_enabled():
                        if _click_checkbox_via_selenium(driver, cb):
                            log("Кликнул по чекбоксу (Selenium fallback).", "ok")
                            clicked_count += 1
                            last_click_at = time.time()
                            clicked_this_round = True
                            break
                except WebDriverException:
                    continue
        if clicked_this_round:
            time.sleep(0.5)
            continue

        # --- 3) Координатный клик по #bcQj6 (закрытый shadow DOM) ---
        try:
            bc = driver.find_element(By.CSS_SELECTOR, "#bcQj6")
            if bc.is_displayed():
                now = time.time()
                if bc_first_seen is None:
                    bc_first_seen = now
                    try:
                        html = bc.get_attribute("outerHTML") or ""
                        log(f"#bcQj6 найден. outerHTML len={len(html)}. "
                            f"Если len не растёт и кликов в DOM не видно — это "
                            f"закрытый shadow DOM, будем кликать по координатам.",
                            "info")
                    except WebDriverException:
                        pass
                # Ждём ~8 сек, чтобы виджет успел отрисоваться
                if now - bc_first_seen >= 8:
                    if clicked_count < max_clicks and now - last_click_at >= 3:
                        if _click_widget_by_coords(driver, bc):
                            clicked_count += 1
                            last_click_at = now
                            log(f"Кликнул по координатам #bcQj6 (попытка {clicked_count}).", "ok")
        except (WebDriverException, NoSuchElementException):
            pass

        # --- Диагностика раз в 5 сек ---
        now = time.time()
        if now - last_log >= 5:
            diag = _diag_turnstile(driver)
            bc_info = diag.get("bcQj6") or {}
            log(
                f"Ищу Turnstile... ({now - start:.0f}s/{timeout}s) "
                f"| iframes={diag.get('iframes_deep', '?')} "
                f"checkboxes={diag.get('checkboxes_deep', '?')} "
                f"roles={diag.get('role_checkbox_deep', '?')} "
                f"shadow={diag.get('shadow_roots', '?')} "
                f"bcQj6={'да' if bc_info else 'нет'}"
                + (f"(ch={bc_info.get('children')},"
                   f"html={bc_info.get('html_len')},"
                   f"{bc_info.get('w')}x{bc_info.get('h')})" if bc_info else "")
                + f" кликов={clicked_count}",
                "info",
            )
            last_log = now

        time.sleep(0.5)

    log(f"Авто-решение Cloudflare не удалось за {timeout}s (кликов: {clicked_count}).", "warn")
    return False


def wait_for_cloudflare_solved(driver, timeout=None) -> bool:
    """Fallback: ждёт, пока пользователь вручную решит капчу."""
    log("Ожидаю РУЧНОГО решения капчи Cloudflare в окне браузера...", "warn")
    start = time.time()
    last_log = start
    while True:
        try:
            if not is_cloudflare_challenge(driver):
                time.sleep(1.0)
                if not is_cloudflare_challenge(driver):
                    log(f"Капча решена вручную за {time.time() - start:.1f}s. Продолжаю.", "ok")
                    return True
        except WebDriverException:
            pass

        now = time.time()
        if now - last_log >= 30:
            log(f"Всё ещё жду решения капчи... прошло {now - start:.0f}s", "info")
            last_log = now

        if timeout and (now - start) > timeout:
            log(f"Таймаут ожидания капчи ({timeout}s).", "err")
            return False
        time.sleep(1.0)


def ensure_no_cloudflare(driver) -> bool:
    """
    Единая точка: если есть Cloudflare — пробует авто-решение (до 90 сек),
    при неудаче ждёт ручного. Возвращает True, если челлендж снят.
    """
    if not is_cloudflare_challenge(driver):
        return True

    if auto_solve_cloudflare_checkbox(driver, timeout=90):
        return True

    log("Авто-решение не сработало, жду ручного подтверждения капчи.", "warn")
    return wait_for_cloudflare_solved(driver)


def _has_search_results(driver) -> bool:
    """True, если на странице есть блоки результатов или надпись 'no results'."""
    try:
        if driver.find_elements(By.CLASS_NAME, "result"):
            return True
        if "no results" in (driver.page_source or "").lower():
            return True
    except WebDriverException:
        pass
    return False


def save_to_file(query_item, timestamp_value, result_value):
    try:
        ts_str = str(timestamp_value).strip() if timestamp_value else ""
        
        if ts_str and ts_str not in ["None", "0", "null", "false"]:
            try:
                date_part = ts_str.replace("T", " ").split(" ")[0]
                parsed_date = datetime.strptime(date_part, "%Y-%m-%d").date()
                today = datetime.now().date()
                days_ago = (today - parsed_date).days
                
                if days_ago == 0:
                    age_status = "сегодня"
                elif days_ago == 1:
                    age_status = "вчера"
                else:
                    age_status = f"{days_ago} дн. назад"
                
                log_string = f"{query_item} [Дата: {date_part} | Возраст: {age_status}] -> {TARGET_CODE_WORD}: {result_value}\n"
                
            except Exception as parse_err:
                log_string = f"{query_item} [{ts_str}] -> {TARGET_CODE_WORD}: {result_value}\n"
        else:
            log_string = f"{query_item} -> {TARGET_CODE_WORD}: {result_value}\n"
            
        with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
            f.write(log_string)
            
    except OSError as e:
        log(f"Не удалось записать результат в файл: {e}", "err")


def process_search_loop(driver, search_items):
    """
    Последовательно выполняет поиск, извлекает временную метку (timestamp) устройства
    и кодовое слово (Serial Number). При появлении капчи Cloudflare — пытается
    решить автоматически, при неудаче ждёт ручного решения, затем продолжает
    с ТОГО ЖЕ элемента (без пропусков).
    """
    idx = 0
    total = len(search_items)
    while idx < total:
        item = search_items[idx]
        log(f"Начинаю обработку элемента [{idx + 1}/{total}]: '{item}'")

        captcha_retries = 0
        max_captcha_retries = 15  # предохранитель от бесконечного цикла

        while True:  # цикл повторов одного и того же item при капче
            if "shodan.io" not in driver.current_url:
                driver.get(SHODAN_URL)
                time.sleep(uniform(0.2, 0.5))

            # Капча могла встретиться ещё до ввода запроса
            if is_cloudflare_challenge(driver):
                if captcha_retries >= max_captcha_retries:
                    log(f"Слишком много капч для '{item}', пропускаю.", "err")
                    break
                captcha_retries += 1
                ensure_no_cloudflare(driver)
                continue

            el = find_first(driver, SEARCH_SELECTORS, label=f"поле поиска для '{item}'")
            if el is None:
                log(f"Не удалось найти поисковую строку для элемента '{item}', пропускаю.", "err")
                break

            click(el, driver)
            el.clear()
            el.send_keys(item)
            el.submit()
            log(f"Отправил поисковый запрос: '{item}'", "ok")

            # Ждём либо результаты, либо капчу (до ~8 сек)
            deadline = time.time() + 8
            captcha_detected = False
            while time.time() < deadline:
                if is_cloudflare_challenge(driver):
                    captcha_detected = True
                    break
                if _has_search_results(driver):
                    break
                time.sleep(0.2)

            # Обработка капчи после отправки запроса
            if captcha_detected or is_cloudflare_challenge(driver):
                if captcha_retries >= max_captcha_retries:
                    log(f"Слишком много капч для '{item}', пропускаю.", "err")
                    break
                captcha_retries += 1
                ensure_no_cloudflare(driver)
                time.sleep(1.0)  # дать странице дорисоваться после челленджа

                # Если после решения капчи результатов нет — повторяем тот же запрос
                if not _has_search_results(driver):
                    log(f"Результатов после капчи нет — повторяю запрос '{item}'.", "info")
                    continue
                # иначе падаем в парсинг ниже

            try:
                page_content = driver.page_source

                # Находим все блоки с классом result
                result_blocks = re.findall(
                    r'<div class="result">.*?</div>\s*</div>\s*</div>',
                    page_content, re.DOTALL,
                )

                if result_blocks:
                    for block in result_blocks:
                        time_match = re.search(
                            r'class="timestamp[^"]*">([^<]+)</div>',
                            block, re.IGNORECASE,
                        )
                        timestamp = time_match.group(1).strip() if time_match else None

                        serial_match = re.search(
                            rf"{re.escape(TARGET_CODE_WORD)}\s*:\s*([A-Za-z0-9_\-]+)",
                            block, re.IGNORECASE,
                        )
                        if serial_match:
                            raw_value = str(serial_match.group(1)).strip()
                            truncated_value = raw_value[:10]
                            log(f"РЕЗУЛЬТАТ ДЛЯ '{item}' [{timestamp}] -> {TARGET_CODE_WORD}: {truncated_value}", "ok")
                            save_to_file(item, timestamp, truncated_value)
                else:
                    # Способ 2 (резервный): парсим через DOM элементы
                    results = driver.find_elements(By.CLASS_NAME, "result")
                    if not results:
                        log(f"На странице результатов для '{item}' ничего не найдено.", "warn")
                    else:
                        for res_el in results:
                            try:
                                ts_el = res_el.find_element(By.CLASS_NAME, "timestamp")
                                timestamp = ts_el.text.strip()
                            except NoSuchElementException:
                                timestamp = None

                            text = res_el.text
                            if TARGET_CODE_WORD.lower() in text.lower():
                                match = re.search(
                                    rf"{re.escape(TARGET_CODE_WORD)}\s*:\s*([A-Za-z0-9_\-]+)",
                                    text, re.IGNORECASE,
                                )
                                if match:
                                    raw_value = str(match.group(1)).strip()
                                    truncated_value = raw_value[:10]
                                    log(f"РЕЗУЛЬТАТ (резервный) ДЛЯ '{item}' [{timestamp}] -> {TARGET_CODE_WORD}: {truncated_value}", "ok")
                                    save_to_file(item, timestamp, truncated_value)

            except Exception as e:
                log(f"Ошибка при парсинге страницы для '{item}': {e}", "err")
                if VERBOSE:
                    traceback.print_exc()

            break  # элемент успешно обработан — выходим из цикла повторов

        idx += 1
        uniform(0.2, 0.4)


def main():
    global VERBOSE
    parser = argparse.ArgumentParser(description="Автоматизация Shodan c парсингом списков слов")
    parser.add_argument("--user-data-dir", default=None)
    parser.add_argument("--profile-dir", default=None)
    parser.add_argument("--verbose", action="store_true", help="Показывать полный traceback при ошибках")
    args = parser.parse_args()
    VERBOSE = args.verbose

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

        # Если Cloudflare выскочил прямо на старте — разбираемся
        if is_cloudflare_challenge(driver):
            ensure_no_cloudflare(driver)

        step(5, total_steps, "Ищу и жму Login/Account -> Continue with Google")
        if not click_login(driver):
            log("Кнопку логина не нашёл — жду, вдруг вы кликнете сами...", "warn")
        time.sleep(0.5)
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
        kill_chrome_zombies()
        os._exit(0) 



if __name__ == "__main__":
    main()
