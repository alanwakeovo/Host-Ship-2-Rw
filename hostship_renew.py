#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import sys
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


SERVER_URL = os.getenv("SERVER_URL", "").strip()
HOSTSHIP_LOGIN = os.getenv("HOSTSHIP_LOGIN", "").strip()
HOSTSHIP_PASSWORD = os.getenv("HOSTSHIP_PASSWORD", "").strip()

TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN", "").strip()
TG_CHAT_ID = os.getenv("TG_CHAT_ID", "").strip()

IS_PROXY = os.getenv("IS_PROXY", "false").lower() == "true"
PROXY_SERVER = os.getenv(
    "PROXY_SERVER",
    "socks5://127.0.0.1:1080"
).strip()

MANUAL_RUN = os.getenv(
    "MANUAL_RUN",
    "false"
).lower() == "true"

HEADLESS_MODE = os.getenv(
    "HEADLESS",
    "auto"
).strip().lower()

BJ_TZ = ZoneInfo("Asia/Shanghai")

STEALTH_INIT_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', {
    get: () => undefined
});
window.chrome = window.chrome || {
    runtime: {},
    loadTimes: function() {},
    csi: function() {},
    app: {}
};
Object.defineProperty(navigator, 'languages', {
    get: () => ['en-US', 'en']
});
Object.defineProperty(navigator, 'plugins', {
    get: () => [1, 2, 3, 4, 5]
});
"""


def log(msg):
    print(
        f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}",
        flush=True
    )


def server_id():
    if not SERVER_URL:
        return "未知"

    return SERVER_URL.rstrip("/").split("/")[-1]


def node_status():
    if IS_PROXY:
        return "✅ 已启用"

    return "⚪ 未启用（直连）"


def get_days(text):
    if not text:
        return None

    match = re.search(
        r"(\d+)\s*Days?",
        text,
        re.I
    )

    if match:
        return int(match.group(1))

    return None


def beijing_now():
    return datetime.now(BJ_TZ)


def estimate_renew_date(status):
    days = get_days(status)

    if days is None:
        return None

    return (
        beijing_now().date()
        + timedelta(days=days)
    )


def tg(text):
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        log("⚠️ Telegram 未配置，跳过通知")
        return False

    try:
        proxies = None

        if IS_PROXY:
            proxies = {
                "http": PROXY_SERVER,
                "https": PROXY_SERVER,
            }

        response = requests.post(
            (
                "https://api.telegram.org/"
                f"bot{TG_BOT_TOKEN}/sendMessage"
            ),
            json={
                "chat_id": TG_CHAT_ID,
                "text": text,
            },
            timeout=20,
            proxies=proxies,
        )

        if response.ok:
            log("✅ Telegram 通知发送成功")
            return True

        log(
            "❌ Telegram 通知失败: "
            + response.text
        )

        return False

    except Exception as exc:
        log(
            f"❌ Telegram 通知异常: {exc}"
        )
        return False


def current_ip():
    try:
        proxies = None

        if IS_PROXY:
            proxies = {
                "http": PROXY_SERVER,
                "https": PROXY_SERVER,
            }

        response = requests.get(
            "https://api.ipify.org",
            timeout=15,
            proxies=proxies,
        )

        if response.ok:
            return response.text.strip()

        return "获取失败"

    except Exception:
        return "获取失败"


def build_check_message(status, ip):
    days = get_days(status)
    renew_date = estimate_renew_date(status)
    now = beijing_now()

    lines = [
        "⏳ Host-Ship 检查完成",
        "",
        f"🖥️ 服务器：#{server_id()}",
        f"🌐 节点状态：{node_status()}",
        f"📍 出口IP：{ip}",
        f"🕗 检查时间：{now.strftime('%Y/%m/%d %H:%M')}",
        "",
        "🔒 当前状态：未到续期时间",
    ]

    if days is not None:
        lines.append(
            f"⏱️ 距离续期：约 {days} 天"
        )

    if renew_date is not None:
        lines.append(
            "📆 预计可续期："
            + renew_date.strftime("%Y/%m/%d")
        )

    if days is None:
        lines.append(
            f"📅 面板状态：{status}"
        )

    lines.append(
        "⏰ 自动检查：每天 08:00（北京时间）"
    )

    return "\n".join(lines)


def build_success_message(before, after, ip):
    before_days = get_days(before)
    after_days = get_days(after)
    now = beijing_now()

    lines = [
        "🎉 Host-Ship 续期成功",
        "",
        f"🖥️ 服务器：#{server_id()}",
        f"🌐 节点状态：{node_status()}",
        f"📍 出口IP：{ip}",
        f"🕗 续期时间：{now.strftime('%Y/%m/%d %H:%M')}",
        "",
    ]

    if before_days is not None:
        lines.append(
            f"📅 续期前：约 {before_days} 天"
        )
    else:
        lines.append(
            f"📅 续期前：{before}"
        )

    if after_days is not None:
        lines.append(
            f"✅ 续期后：约 {after_days} 天"
        )
    else:
        lines.append(
            f"✅ 续期后：{after}"
        )

    lines.append(
        "⏰ 自动检查：每天 08:00（北京时间）"
    )

    return "\n".join(lines)


def build_error_message(title, reason, ip):
    now = beijing_now()

    return (
        f"{title}\n\n"
        f"🖥️ 服务器：#{server_id()}\n"
        f"🌐 节点状态：{node_status()}\n"
        f"📍 出口IP：{ip}\n"
        f"🕗 检查时间：{now.strftime('%Y/%m/%d %H:%M')}\n\n"
        f"⚠️ 原因：{reason}"
    )


def first_visible(page, selectors):
    for selector in selectors:
        locator = page.locator(
            selector
        ).first

        try:
            if (
                locator.count()
                and locator.is_visible()
            ):
                return locator

        except Exception:
            pass

    return None


def is_submit_ready(submit):
    try:
        if not submit.is_visible():
            return False

        if submit.is_disabled():
            return False

        btn_text = (submit.inner_text() or "").strip().lower()
        if "security check" in btn_text:
            return False

        return True

    except Exception:
        return False


def click_turnstile_box(page, password_locator=None, submit_locator=None):
    """尝试定位并点击 Cloudflare Turnstile 验证框"""
    # 1. 优先尝试直接从 frames 中点击 Cloudflare 内部复选框
    for frame in page.frames:
        frame_url = (frame.url or "").lower()
        if "challenges.cloudflare.com" in frame_url or "turnstile" in frame_url:
            try:
                cb = frame.locator('input[type="checkbox"], [role="checkbox"]').first
                if cb.count() and cb.is_visible():
                    cb.click(timeout=3000)
                    log("🖱️ 已通过 iframe 内部元素点击 Turnstile")
                    return True
            except Exception:
                pass

            try:
                frame_el = frame.frame_element()
                box = frame_el.bounding_box()
                if box and box["width"] >= 100 and box["height"] >= 35:
                    target_x = box["x"] + 28
                    target_y = box["y"] + box["height"] / 2
                    page.mouse.move(target_x, target_y, steps=8)
                    time.sleep(0.15)
                    page.mouse.click(target_x, target_y)
                    log("🖱️ 已通过 iframe 坐标点击 Turnstile")
                    return True
            except Exception:
                pass

    # 2. 查找常见的 Turnstile 外层容器或 iframe 选择器
    turnstile_selectors = [
        'iframe[src*="challenges.cloudflare.com"]',
        'iframe[src*="turnstile"]',
        'iframe[title*="Cloudflare" i]',
        'iframe[title*="widget" i]',
        '.cf-turnstile',
        '[data-sitekey]',
        '[id*="turnstile" i]',
        '[class*="turnstile" i]',
    ]

    for selector in turnstile_selectors:
        try:
            loc = page.locator(selector).first
            if loc.count() and loc.is_visible():
                box = loc.bounding_box()
                if box and box["width"] >= 150 and box["height"] >= 40:
                    target_x = box["x"] + 28
                    target_y = box["y"] + box["height"] / 2
                    page.mouse.move(target_x, target_y, steps=8)
                    time.sleep(0.15)
                    page.mouse.click(target_x, target_y)
                    log(f"🖱️ 已通过容器 ({selector}) 坐标点击 Turnstile")
                    return True
        except Exception:
            pass

    # 3. 针对闭合 Shadow DOM：扫描表单内符合 Turnstile 尺寸 (约 300x65) 的块级元素
    try:
        divs = page.locator("form div")
        count = divs.count()
        for i in range(count):
            div = divs.nth(i)
            if not div.is_visible():
                continue
            box = div.bounding_box()
            if (
                box
                and 240 <= box["width"] <= 420
                and 55 <= box["height"] <= 80
            ):
                # 排除包含输入框或按钮的普通容器
                if (
                    div.locator("input, button").count() == 0
                ):
                    target_x = box["x"] + 28
                    target_y = box["y"] + box["height"] / 2
                    page.mouse.move(target_x, target_y, steps=8)
                    time.sleep(0.15)
                    page.mouse.click(target_x, target_y)
                    log("🖱️ 已通过表单内尺寸匹配点击 Turnstile 区域")
                    return True
    except Exception:
        pass

    # 4. 根据密码框与提交按钮之间的空白区域推算 Turnstile 坐标
    if password_locator and submit_locator:
        try:
            pw_box = password_locator.bounding_box()
            sub_box = submit_locator.bounding_box()
            if pw_box and sub_box:
                pw_bottom = pw_box["y"] + pw_box["height"]
                gap = sub_box["y"] - pw_bottom
                if gap >= 50:
                    target_x = sub_box["x"] + 28
                    target_y = pw_bottom + (gap / 2)
                    page.mouse.move(target_x, target_y, steps=8)
                    time.sleep(0.15)
                    page.mouse.click(target_x, target_y)
                    log("🖱️ 已通过密码框与提交按钮间距点击 Turnstile 区域")
                    return True
        except Exception:
            pass

    return False


def wait_and_solve_turnstile(
    page,
    submit,
    password_locator=None,
    timeout_sec=35,
):
    """等待安全验证完成，必要时主动点击 Turnstile"""
    start_time = time.time()
    click_attempts = 0

    while time.time() - start_time < timeout_sec:
        if is_submit_ready(submit):
            log("✅ 安全验证已通过，登录按钮已激活")
            return True

        elapsed = time.time() - start_time
        # 页面加载 3 秒后若按钮仍禁用，每隔 5 秒尝试点击一次验证框
        if elapsed >= 3.0 and int(elapsed) // 5 > click_attempts:
            click_attempts += 1
            log(f"⏳ 登录按钮仍禁用，尝试触发安全验证 (第 {click_attempts} 次)...")
            click_turnstile_box(
                page,
                password_locator=password_locator,
                submit_locator=submit,
            )

        page.wait_for_timeout(1000)

    return is_submit_ready(submit)


def login_if_needed(page):
    page.goto(
        SERVER_URL,
        wait_until="domcontentloaded",
        timeout=60000,
    )

    page.wait_for_timeout(3000)

    # 如果遇到全屏 Cloudflare 五秒盾，先尝试点击等待
    for _ in range(3):
        title_text = (page.title() or "").lower()
        body_lower = page.locator("body").inner_text().lower()
        if (
            "just a moment" in title_text
            or "verify you are human" in body_lower
        ):
            log("🛡️ 检测到 Cloudflare 全屏拦截页，尝试通过...")
            click_turnstile_box(page)
            page.wait_for_timeout(4000)
        else:
            break

    body = page.locator(
        "body"
    ).inner_text().lower()

    if (
        "/server/" in page.url
        and "password" not in body
    ):
        return True

    email = first_visible(
        page,
        [
            'input[name="email"]',
            'input[type="email"]',
            'input[name="username"]',
            'input[autocomplete="username"]',
        ],
    )

    password = first_visible(
        page,
        [
            'input[name="password"]',
            'input[type="password"]',
            'input[autocomplete="current-password"]',
        ],
    )

    if not email or not password:
        log(
            "❌ 没找到登录框，"
            f"当前页面: {page.url}"
        )
        return False

    if (
        not HOSTSHIP_LOGIN
        or not HOSTSHIP_PASSWORD
    ):
        log(
            "❌ 缺少 HOSTSHIP_LOGIN "
            "/ HOSTSHIP_PASSWORD"
        )
        return False

    log("🔐 正在填写登录信息...")

    email.click()
    page.wait_for_timeout(200)
    email.fill(HOSTSHIP_LOGIN)

    page.wait_for_timeout(300)

    password.click()
    page.wait_for_timeout(200)
    password.fill(HOSTSHIP_PASSWORD)

    submit = first_visible(
        page,
        [
            'button[type="submit"]',
            'button:has-text("Login")',
            'button:has-text("Sign in")',
            'button:has-text("Log in")',
        ],
    )

    if not submit:
        log("❌ 没找到登录按钮")
        return False

    if not wait_and_solve_turnstile(
        page,
        submit,
        password_locator=password,
        timeout_sec=35,
    ):
        btn_label = ""
        try:
            btn_label = submit.inner_text().strip()
        except Exception:
            pass
        log(
            "⚠️ 登录按钮始终处于禁用状态 "
            f"({btn_label or 'disabled'})，未能通过 Cloudflare 安全验证"
        )
        return False

    log("🚀 点击登录按钮...")
    try:
        submit.click(timeout=10000)
    except PlaywrightTimeoutError:
        log("❌ 点击登录按钮超时")
        return False

    # 等待登录跳转完成
    for _ in range(10):
        page.wait_for_timeout(1500)
        if "/auth/" not in page.url and "/login" not in page.url:
            break

    text = page.locator(
        "body"
    ).inner_text().lower()

    challenge_words = [
        "captcha",
        "verify you are human",
        "complete the security check",
    ]

    if (
        "/server/" not in page.url
        and any(word in text for word in challenge_words)
    ):
        log(
            "⚠️ 检测到验证码/"
            "安全验证未通过"
        )
        return False

    if "/server/" not in page.url:
        page.goto(
            SERVER_URL,
            wait_until="domcontentloaded",
            timeout=60000,
        )
        page.wait_for_timeout(3000)

    return "/server/" in page.url


def get_renewal_text(page):
    text = page.locator(
        "body"
    ).inner_text()

    patterns = [
        r"Renewal\s+in\s+\d+\s+Days?",
        r"Renew\s+in\s+\d+\s+Days?",
        r"\d+\s+Days?\s+until\s+renewal",
    ]

    for pattern in patterns:
        match = re.search(
            pattern,
            text,
            re.I,
        )

        if match:
            return match.group(0)

    if re.search(
        r"Renew\s+Limit\s+Reached",
        text,
        re.I,
    ):
        return "Renew Limit Reached"

    return "未识别"


def find_renew_button(page):
    candidates = [
        page.get_by_role(
            "button",
            name=re.compile(
                r"^Renew(?:\s+Now|\s+Server)?$",
                re.I,
            ),
        ),
        page.get_by_role(
            "link",
            name=re.compile(
                r"^Renew(?:\s+Now|\s+Server)?$",
                re.I,
            ),
        ),
        page.locator(
            'button:has-text("Renew")'
        ),
        page.locator(
            'a:has-text("Renew")'
        ),
    ]

    for group in candidates:
        try:
            count = group.count()

            for i in range(count):
                item = group.nth(i)

                if item.is_visible():
                    return item

        except Exception:
            pass

    return None


def confirm_renewal(page):
    """Wait for the renewal dialog and click the real submit button."""
    title = page.get_by_text(
        re.compile(
            r"Confirm\s+server\s+renewal",
            re.I,
        )
    ).first

    try:
        title.wait_for(
            state="visible",
            timeout=8000,
        )
    except Exception:
        log("❌ 点击 Renew 后未出现续期确认弹窗")
        return False

    confirm_buttons = [
        page.get_by_role(
            "dialog"
        ).last.get_by_role(
            "button",
            name=re.compile(
                r"^Renew\s+now$",
                re.I,
            ),
        ),
        page.get_by_role(
            "button",
            name=re.compile(
                r"^Renew\s+now$",
                re.I,
            ),
        ),
        page.locator(
            'button:has-text("Renew now")'
        ),
    ]

    for group in confirm_buttons:
        try:
            count = group.count()

            for i in range(count):
                button = group.nth(i)

                if (
                    button.is_visible()
                    and button.is_enabled()
                ):
                    log(
                        "✅ 确认弹窗已打开，"
                        "点击 Renew now..."
                    )
                    button.click()
                    return True

        except Exception:
            pass

    log("❌ 确认弹窗中未找到可点击的 Renew now")
    return False


def renewal_succeeded(before, after, body_text):
    text = body_text.lower()
    success_words = [
        "renewed successfully",
        "renewal successful",
        "successfully renewed",
        "renew limit reached",
    ]

    if any(word in text for word in success_words):
        return True

    before_days = get_days(before)
    after_days = get_days(after)

    return (
        before_days is not None
        and after_days is not None
        and after_days > before_days
    )


def wait_for_renewal_result(page, before):
    """Poll once, then reload to avoid reading a stale SPA state."""
    after = get_renewal_text(page)

    for attempt in range(5):
        body_text = page.locator(
            "body"
        ).inner_text()
        after = get_renewal_text(page)

        if renewal_succeeded(
            before,
            after,
            body_text,
        ):
            return True, after

        page.wait_for_timeout(2000)

        if attempt == 1:
            page.reload(
                wait_until="domcontentloaded",
                timeout=60000,
            )
            page.wait_for_timeout(2000)

    return False, after


def resolve_headless():
    if HEADLESS_MODE in ("true", "1", "yes"):
        return True
    if HEADLESS_MODE in ("false", "0", "no"):
        return False
    # auto 模式：若存在 DISPLAY（如 xvfb-run），优先使用有头模式降低风控
    return not bool(os.getenv("DISPLAY"))


def main():
    if not SERVER_URL.startswith(
        "https://panel.host-ship.com/server/"
    ):
        log("❌ SERVER_URL 不正确")

        tg(
            "❌ Host-Ship 配置错误\n"
            "SERVER_URL 不是服务器详情页地址"
        )

        return 1

    log("======================================")
    log(" Host-Ship Free Auto Renew")
    log("======================================")

    log(
        f"🌐 节点状态：{node_status()}"
    )

    ip = current_ip()

    log(
        f"📍 当前出口IP：{ip}"
    )

    use_headless = resolve_headless()
    log(
        f"🖥️ 浏览器模式：{'Headless' if use_headless else 'Headed (XVFB/GUI)'}"
    )

    with sync_playwright() as p:
        launch_args = [
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
            "--window-size=1440,1000",
        ]

        browser = p.chromium.launch(
            headless=use_headless,
            proxy={
                "server": PROXY_SERVER
            }
            if IS_PROXY
            else None,
            args=launch_args,
        )

        # 获取当前浏览器原生 UA 并抹除 HeadlessChrome 标记，确保平台与内核版本完全一致
        temp_page = browser.new_page()
        native_ua = temp_page.evaluate("() => navigator.userAgent")
        temp_page.close()
        clean_ua = native_ua.replace("HeadlessChrome/", "Chrome/")

        context = browser.new_context(
            viewport={
                "width": 1440,
                "height": 1000,
            },
            user_agent=clean_ua,
            locale="en-US",
        )
        context.add_init_script(STEALTH_INIT_SCRIPT)

        page = context.new_page()

        try:
            if not login_if_needed(page):
                page.screenshot(
                    path="hostship_login_fail.png",
                    full_page=True,
                )

                tg(
                    build_error_message(
                        "❌ Host-Ship 登录失败",
                        "登录失败或遇到 Cloudflare 安全验证拦截",
                        ip,
                    )
                )

                return 1

            log("✅ 登录成功")

            before = get_renewal_text(page)

            log(
                f"📅 当前续期状态：{before}"
            )

            body = page.locator(
                "body"
            ).inner_text()

            if re.search(
                r"Renew\s+Limit\s+Reached",
                body,
                re.I,
            ):
                log(
                    "⏳ 目前未到续期时间，"
                    "不进行操作"
                )

                if MANUAL_RUN:
                    tg(
                        build_check_message(
                            before,
                            ip,
                        )
                    )

                return 0

            button = find_renew_button(page)

            if not button:
                page.screenshot(
                    path="hostship_no_renew_button.png",
                    full_page=True,
                )

                tg(
                    build_error_message(
                        "⚠️ Host-Ship 需要检查",
                        (
                            "没有找到可用的 "
                            f"Renew 按钮；{before}"
                        ),
                        ip,
                    )
                )

                return 1

            try:
                disabled = button.is_disabled()

            except Exception:
                disabled = False

            if disabled:
                log(
                    "⏳ Renew 按钮当前不可点击"
                )

                if MANUAL_RUN:
                    tg(
                        build_check_message(
                            before,
                            ip,
                        )
                    )

                return 0

            log(
                "🔄 已到续期窗口，"
                "点击 Renew..."
            )

            button.click()

            if not confirm_renewal(page):
                page.screenshot(
                    path="hostship_confirm_fail.png",
                    full_page=True,
                )

                tg(
                    build_error_message(
                        "❌ Host-Ship 续期确认失败",
                        (
                            "点击第一层 Renew 后，"
                            "未能点击确认弹窗中的 Renew now"
                        ),
                        ip,
                    )
                )

                return 1

            success, after = wait_for_renewal_result(
                page,
                before,
            )

            if success:
                log(
                    "✅ 续期成功："
                    f"{before} -> {after}"
                )

                tg(
                    build_success_message(
                        before,
                        after,
                        ip,
                    )
                )

                return 0

            page.screenshot(
                path="hostship_renew_uncertain.png",
                full_page=True,
            )

            log(
                "⚠️ 已点击续期，"
                "但无法确认结果"
            )

            tg(
                build_error_message(
                    "⚠️ Host-Ship 续期结果需要检查",
                    (
                        f"续期前：{before}；"
                        f"续期后：{after}"
                    ),
                    ip,
                )
            )

            return 1

        except Exception as exc:
            log(
                f"❌ 运行异常：{exc}"
            )

            try:
                page.screenshot(
                    path="hostship_error.png",
                    full_page=True,
                )
            except Exception:
                pass

            tg(
                build_error_message(
                    "❌ Host-Ship 自动续期异常",
                    str(exc),
                    ip,
                )
            )

            return 1

        finally:
            browser.close()


if __name__ == "__main__":
    sys.exit(main())
