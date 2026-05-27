#!/usr/bin/env python

import os
import sys
import time
import base64
import common
import hashlib
import binascii
import requests
from getpass import getpass
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from optparse import OptionParser

PY3 = sys.version_info[0] == 3

if PY3:
    from urllib.parse import urlencode
    from urllib.parse import urlparse, parse_qsl
else:
    from urllib import urlencode
    from urlparse import urlparse, parse_qsl


def _wait_for_any(driver, locators, timeout=15):
    """Return the first element found from a list of (By, selector) locators."""
    end = time.time() + timeout
    last_error = None
    while time.time() < end:
        for locator in locators:
            try:
                el = driver.find_element(*locator)
                if el.is_displayed():
                    return el
            except Exception as exc:
                last_error = exc
        time.sleep(0.25)
    raise TimeoutException("Could not find any of: %s" % (locators,)) from last_error


def _click_if_present(driver, locators, timeout=5):
    try:
        el = _wait_for_any(driver, locators, timeout=timeout)
        el.click()
        return True
    except Exception:
        return False


def _create_chrome_driver(opts):
    # Prefer a local chromedriver if the user placed one next to the script, but
    # otherwise let Selenium Manager obtain/use the correct driver automatically.
    candidates = []
    if sys.platform == 'win32':
        candidates.append("chromedriver.exe")
    candidates.extend([
        "/usr/bin/chromedriver",
        "/usr/lib/chromium-browser/chromedriver",
        "/usr/local/bin/chromedriver",
        "./chromedriver",
    ])

    for path in candidates:
        if os.path.isfile(path):
            service = ChromeService(executable_path=path)
            return webdriver.Chrome(service=service, options=opts)

    return webdriver.Chrome(options=opts)


def _create_firefox_driver():
    candidates = []
    if sys.platform == 'win32':
        candidates.append("geckodriver.exe")
    candidates.extend([
        "/usr/bin/geckodriver",
        "/usr/local/bin/geckodriver",
        "./geckodriver",
    ])

    for path in candidates:
        if os.path.isfile(path):
            service = FirefoxService(executable_path=path)
            return webdriver.Firefox(service=service)

    return webdriver.Firefox()


def _automated_login(driver, username, password):
    wait = WebDriverWait(driver, 20)

    # Amazon often shows email first, then password on the next screen.
    email_box = wait.until(EC.presence_of_element_located((By.ID, 'ap_email')))
    email_box.clear()
    email_box.send_keys(username)

    # Some flows have a Continue button after email. Others already show password.
    _click_if_present(driver, [
        (By.ID, 'continue'),
        (By.CSS_SELECTOR, 'input[type="submit"][aria-labelledby="continue-announce"]'),
        (By.CSS_SELECTOR, 'input.a-button-input[type="submit"]'),
    ], timeout=4)

    password_box = wait.until(EC.presence_of_element_located((By.ID, 'ap_password')))
    password_box.clear()
    password_box.send_keys(password)

    # Click sign-in when present; otherwise submit the password field.
    clicked = _click_if_present(driver, [
        (By.ID, 'signInSubmit'),
        (By.CSS_SELECTOR, 'input[type="submit"][aria-labelledby="auth-signin-button-announce"]'),
        (By.CSS_SELECTOR, 'input.a-button-input[type="submit"]'),
    ], timeout=4)
    if not clicked:
        password_box.submit()


def fetch_activation_bytes(username, password, options):
    base_url = 'https://www.audible.com/'
    base_url_license = 'https://www.audible.com/'
    lang = options.lang

    # Step 0
    opts = webdriver.ChromeOptions()
    opts.add_argument("user-agent=Mozilla/5.0 (Windows NT 6.1; WOW64; Trident/7.0; AS; rv:11.0) like Gecko")
    if not (os.getenv("DEBUG") or options.debug):
        opts.add_argument('--headless')
    opts.add_argument('--no-sandbox')
    opts.add_argument('--disable-dev-shm-usage')

    # Step 1
    if '@' in username:  # Amazon login using email address
        login_url = "https://www.amazon.com/ap/signin?"
    else:  # Audible member login using username (untested!)
        login_url = "https://www.audible.com/sign-in/ref=ap_to_private?forcePrivateSignIn=true&rdPath=https%3A%2F%2Fwww.audible.com%2F%3F"
    if lang == "uk":
        login_url = login_url.replace('.com', ".co.uk")
        base_url = base_url.replace('.com', ".co.uk")
    elif lang == "jp":
        login_url = login_url.replace('.com', ".co.jp")
        base_url = base_url.replace('.com', ".co.jp")
    elif lang == "au":
        login_url = login_url.replace('.com', ".com.au")
        base_url = base_url.replace('.com', ".com.au")
    elif lang == "in":
        login_url = login_url.replace('.com', ".in")
        base_url = base_url.replace('.com', ".in")
    elif lang != "us":  # something more clever might be needed
        login_url = login_url.replace('.com', "." + lang)
        base_url = base_url.replace('.com', "." + lang)

    if PY3:
        player_id = base64.encodebytes(hashlib.sha1(b"").digest()).rstrip()  # keep this same to avoid hogging activation slots
        player_id = player_id.decode("ascii")
    else:
        player_id = base64.encodestring(hashlib.sha1(b"").digest()).rstrip()
    if options.player_id:
        player_id = base64.encodestring(binascii.unhexlify(options.player_id)).rstrip()
    print("[*] Player ID is %s" % player_id)

    payload = {
        'openid.ns': 'http://specs.openid.net/auth/2.0',
        'openid.identity': 'http://specs.openid.net/auth/2.0/identifier_select',
        'openid.claimed_id': 'http://specs.openid.net/auth/2.0/identifier_select',
        'openid.mode': 'logout',
        'openid.assoc_handle': 'amzn_audible_' + lang,
        'openid.return_to': base_url + 'player-auth-token?playerType=software&playerId=%s=&bp_ua=y&playerModel=Desktop&playerManufacturer=Audible' % (player_id)
    }

    if options.firefox:
        driver = _create_firefox_driver()
    else:
        driver = _create_chrome_driver(opts)

    query_string = urlencode(payload)
    url = login_url + query_string
    driver.get(base_url + '?ipRedirectOverride=true')
    driver.get(url)

    if os.getenv("DEBUG") or options.debug:
        print("[!] DEBUG/manual mode: finish the Amazon/Audible login in the browser window.")
        print("[!] If you receive an OTP, enter it in the browser page, not in this console.")
        if PY3:
            input("[!] After the browser has finished signing in/redirecting, press Enter here to continue...")
        else:
            raw_input("[!] After the browser has finished signing in/redirecting, press Enter here to continue...")
    else:
        _automated_login(driver, username, password)
        time.sleep(3)  # give the page some time to load

        # If Amazon asks for OTP/CAPTCHA/security checks, headless automation cannot reliably finish it.
        # Pause here so the user can rerun with --debug and complete the flow in a visible browser.
        page = driver.page_source.lower()
        current = driver.current_url.lower()
        challenge_words = ["otp", "one time password", "captcha", "challenge", "verification required", "authentication required"]
        if any(word in page or word in current for word in challenge_words):
            print("[!] Amazon/Audible appears to require OTP, CAPTCHA, or another security challenge.")
            print("[!] Rerun with --debug and complete the login in the visible browser window.")
            print("[!] Example: python .\\audible-activator-selenium4-manual-login.py --debug")
            driver.quit()
            return

        # Keep the original pause behavior, but clarify that OTP goes in browser/debug mode, not here.
        msg = "\nATTENTION: If login is not complete, rerun with --debug and finish it in the browser. Press Enter to continue..."
        if PY3:
            input(msg)
        else:
            raw_input(msg)

    # Step 2
    driver.get(base_url + 'player-auth-token?playerType=software&bp_ua=y&playerModel=Desktop&playerId=%s&playerManufacturer=Audible&serial=' % (player_id))
    time.sleep(2)
    current_url = driver.current_url
    o = urlparse(current_url)
    data = dict(parse_qsl(o.query))

    if "playerToken" not in data:
        print("[!] Login did not produce a playerToken, so activation cannot continue.")
        print("[!] Current URL: %s" % current_url)
        print("[!] Try rerunning with --debug, complete every login/OTP/CAPTCHA step in the browser, then press Enter here only after the browser redirects/finishes.")
        try:
            driver.save_screenshot("audible-activator-login-state.png")
            print("[!] Saved screenshot: audible-activator-login-state.png")
        except Exception:
            pass
        driver.quit()
        return

    # Step 2.5, switch User-Agent to "Audible Download Manager"
    headers = {
        'User-Agent': "Audible Download Manager",
    }
    cookies = driver.get_cookies()
    s = requests.Session()
    for cookie in cookies:
        s.cookies.set(cookie['name'], cookie['value'])

    # Step 3, de-register first, in order to stop hogging all activation slots
    # (there are 8 of them!)
    durl = base_url_license + 'license/licenseForCustomerToken?' \
        + 'customer_token=' + data["playerToken"] + "&action=de-register"
    s.get(durl, headers=headers)

    # Step 4
    url = base_url_license + 'license/licenseForCustomerToken?' \
        + 'customer_token=' + data["playerToken"]
    response = s.get(url, headers=headers)

    with open("activation.blob", "wb") as f:
        f.write(response.content)
    activation_bytes, _ = common.extract_activation_bytes(response.content)
    print("activation_bytes: " + activation_bytes)

    # Step 5 (de-register again to stop filling activation slots)
    s.get(durl, headers=headers)

    time.sleep(8)
    driver.quit()


if __name__ == "__main__":
    parser = OptionParser(usage="Usage: %prog [options]", version="%prog 0.2")
    parser.add_option("-d", "--debug",
                      action="store_true",
                      dest="debug",
                      default=False,
                      help="run program in debug/manual mode; opens a visible browser for 2FA/CAPTCHA/security screens")
    parser.add_option("-f", "--firefox",
                      action="store_true",
                      dest="firefox",
                      default=False,
                      help="use this option to use firefox instead of chrome",)
    parser.add_option("-l", "--lang",
                      action="store",
                      dest="lang",
                      default="us",
                      help="us (default) / au / in / de / fr / jp / uk (untested)",)
    parser.add_option("-p",
                      action="store",
                      dest="player_id",
                      default=None,
                      help="Player ID in hex (for debugging, not for end users)",)
    parser.add_option("--username",
                      action="store",
                      dest="username",
                      default=False,
                      help="Audible username, use along with the --password option")
    parser.add_option("--password",
                      action="store",
                      dest="password",
                      default=False,
                      help="Audible password")
    (options, args) = parser.parse_args()

    if options.username and options.password:
        username = options.username
        password = options.password
    else:
        if PY3:
            username = input("Username: ")
        else:
            username = raw_input("Username: ")
        password = getpass("Password: ")

    fetch_activation_bytes(username, password, options)
