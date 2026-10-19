import re
import secrets
import threading
from pathlib import Path

import pytest
from werkzeug.serving import make_server

from app import create_app
from database import db
from institutions import ADMIN_EMAIL
from maintenance import setup_admin
from tests_helpers import registration, send

playwright = pytest.importorskip("playwright.sync_api")


@pytest.fixture
def browser_site(tmp_path):
    mailbox = []
    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "browser-tests",
            "DATABASE": str(tmp_path / "browser.sqlite"),
            "TEST_MAILER": mailbox.append,
        }
    )
    password = secrets.token_urlsafe(20)
    with app.app_context():
        setup_admin(db(), password)
    peer = app.test_client()
    send(peer, "register", data=registration(name="Study Partner", email="partner@dut4life.ac.za"))
    code = re.search(
        r"code is: ([0-9]{6})", mailbox[-1].get_body(preferencelist=("plain",)).get_content()
    ).group(1)
    send(peer, "verify", data={"code": code})
    send(
        peer,
        "profile",
        "PUT",
        {
            "name": "Study Partner",
            "institution_id": 3,
            "programme": "Computer Science",
            "year": 2,
            "skills": ["Python"],
            "needs": [{"topic": "Algorithms", "priority": 3}],
            "modules": ["Computer Science"],
            "preferences": ["Online"],
            "interests": ["Music"],
            "availability": [{"day": "Monday", "start": "16:00", "end": "18:00"}],
        },
    )
    server = make_server("127.0.0.1", 0, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    with playwright.sync_playwright() as p:
        edge = Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe")
        try:
            browser = p.chromium.launch(
                executable_path=str(edge) if edge.exists() else None, headless=True
            )
        except playwright.Error as e:
            server.shutdown()
            pytest.skip(str(e))
        yield browser, f"http://127.0.0.1:{server.server_port}", mailbox, password, peer
        browser.close()
    server.shutdown()
    thread.join()


def enroll(page, url, mailbox):
    page.goto(url)
    landing_copy_size = page.locator(".landing-copy").evaluate(
        "(node) => parseFloat(getComputedStyle(node).fontSize)"
    )
    assert landing_copy_size >= 16
    assert page.locator("body").get_attribute("class") is None
    assert page.get_by_role("heading", name="Great things are learned together.").is_visible()
    assert page.locator(".landing-feature").count() == 3
    assert page.locator("#faqs details").count() == 4
    page.get_by_role("button", name="Get started").click()
    page.get_by_label("Full name").fill("New Learner")
    email = page.get_by_label("Student email", exact=True)
    email.fill("221NEW")
    page.get_by_label("University", exact=True).select_option("20")
    assert (
        email.input_value() == "221NEW"
        and page.locator("#email-suffix").inner_text() == "@tuks.co.za"
    )
    page.get_by_label("University", exact=True).select_option("3")
    assert page.locator("#email-suffix").inner_text() == "@dut4life.ac.za"
    page.get_by_label("Programme").fill("BSc Computer Science")
    page.get_by_label("Password", exact=True).fill("StrongStudentPassword123")
    page.get_by_role("button", name="Create account").click()
    page.get_by_role("heading", name="Check your student inbox.").wait_for()
    code = re.search(
        r"code is: ([0-9]{6})", mailbox[-1].get_body(preferencelist=("plain",)).get_content()
    ).group(1)
    page.get_by_label("Digit 1", exact=True).focus()
    page.keyboard.insert_text(code[0])
    assert page.get_by_label("Digit 2", exact=True).evaluate(
        "(node)=>node===document.activeElement"
    )
    # Exercise real clipboard paste without clipboard permission: dispatch a ClipboardEvent.
    page.get_by_label("Digit 1", exact=True).evaluate(
        "(node,code)=>{const clipboard=new DataTransfer();clipboard.setData('text',code);node.dispatchEvent(new ClipboardEvent('paste',{clipboardData:clipboard,bubbles:true,cancelable:true}));}",
        code,
    )
    assert page.get_by_label("Digit 6", exact=True).input_value() == code[-1]
    page.get_by_role("button", name="Verify email", exact=True).click()
    page.get_by_role("heading", name="People to learn with").wait_for()
    dashboard_date_size = page.locator(".dashboard-date").evaluate(
        "(node) => parseFloat(getComputedStyle(node).fontSize)"
    )
    peer_time_size = page.locator(".dashboard-peer-time").first.evaluate(
        "(node) => parseFloat(getComputedStyle(node).fontSize)"
    )
    assert dashboard_date_size >= 12
    assert peer_time_size >= 11


def test_signup_verification_desktop_and_student_flow(browser_site):
    browser, url, mailbox, _, peer = browser_site
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    enroll(page, url, mailbox)
    page.locator(".nav").get_by_role("button", name="My profile").click()
    page.get_by_label("About you").fill("Verified student profile")
    page.get_by_label("Skills & strengths").fill("Algorithms")
    page.get_by_label("Computer Science", exact=True).check()
    page.get_by_role("button", name="Add a learning need").click()
    page.get_by_label("Learning need", exact=True).fill("Python")
    page.get_by_role("button", name="Save your profile").click()
    page.get_by_text("Profile saved. Your matches are up to date.").wait_for()
    page.locator(".nav").get_by_role("button", name="Find peers").click()
    page.get_by_label("Search peers").fill("Partner")
    assert page.locator(".peer-card").count() == 1
    page.get_by_role("button", name="View profile", exact=True).click()
    page.locator("dialog").get_by_role("heading", name="Study Partner").wait_for()
    page.get_by_role("button", name="Close dialog").click()
    page.locator("[data-connect]").click()
    page.get_by_role("button", name="Request pending").wait_for()
    connection = peer.get("/api/activity").json["connections"][0]
    send(peer, f"connections/{connection['id']}", "PATCH", {"status": "accepted"})
    page.reload()
    page.get_by_role("heading", name="People to learn with").wait_for()
    page.get_by_role("button", name="Plan a session").click()
    page.locator("dialog").get_by_role("heading", name="Make a little time to learn.").wait_for()
    assert page.get_by_label("Study partner").locator("option").count() == 1
    page.get_by_role("button", name="Close dialog").click()
    page.locator(".nav").get_by_role("button", name="Universities").click()
    page.get_by_role("heading", name="One community. 26 universities.").wait_for()
    assert page.locator(".institution-card").count() == 26
    page.get_by_label("Search universities").fill("Pretoria")
    assert page.locator(".institution-card").count() == 1
    page.locator(".nav").get_by_role("button", name="Overview").click()
    Path("artifacts").mkdir(exist_ok=True)
    page.screenshot(path="artifacts/dashboard-desktop.png", full_page=True)
    assert not errors, errors
    page.close()


def test_mobile_verification_and_navigation(browser_site):
    browser, url, mailbox, _, _ = browser_site
    page = browser.new_page(
        viewport={"width": 390, "height": 844},
        is_mobile=True,
        has_touch=True,
        reduced_motion="reduce",
    )
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    enroll(page, url, mailbox)
    assert page.evaluate("document.documentElement.scrollWidth<=window.innerWidth")
    page.get_by_role("button", name="Open navigation").click()
    page.locator(".nav").get_by_role("button", name="My profile").click()
    page.get_by_role("heading", name="A profile that feels like you").wait_for()
    assert page.evaluate("document.documentElement.scrollWidth<=window.innerWidth")
    page.get_by_role("button", name="Open navigation").click()
    page.locator(".nav").get_by_role("button", name="Overview").click()
    Path("artifacts").mkdir(exist_ok=True)
    page.screenshot(path="artifacts/dashboard-mobile.png", full_page=True)
    assert not errors, errors
    page.close()


def test_separate_admin_reset_and_dashboard(browser_site):
    browser, url, _, password, _ = browser_site
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(url + "/?login=1")
    page.get_by_label("Sign in as").select_option("admin")
    page.get_by_label("Email address").fill(ADMIN_EMAIL)
    page.get_by_label("Password", exact=True).fill(password)
    page.get_by_role("button", name="Sign in", exact=True).last.click()
    page.get_by_role("heading", name="Set your administrator password.").wait_for()
    changed = secrets.token_urlsafe(20)
    page.get_by_label("New password").fill(changed)
    page.get_by_label("Confirm password").fill(changed)
    page.get_by_role("button", name="Save password").click()
    page.get_by_role("heading", name="Community at a glance").wait_for()
    assert (
        "/admin/overview" in page.url
        and page.get_by_role("button", name="Find peers").count() == 0
        and page.get_by_role("button", name="My profile").count() == 0
    )
    page.locator(".nav").get_by_role("button", name="Students", exact=True).click()
    page.get_by_role("heading", name="Student management").wait_for()
    page.get_by_label("Search students").fill("partner")
    page.get_by_role("button", name="Search", exact=True).click()
    page.get_by_role("button", name="Detail").click()
    page.locator("dialog").get_by_role("heading", name="Study Partner").wait_for()
    page.get_by_role("button", name="Close dialog").click()
    page.locator(".nav").get_by_role("button", name="Overview").click()
    page.get_by_role("heading", name="Community at a glance").wait_for()
    Path("artifacts").mkdir(exist_ok=True)
    page.screenshot(path="artifacts/admin-desktop.png", full_page=True)
    assert not errors, errors
    page.close()


def test_forgot_password_button_and_email_reset(browser_site):
    browser, url, mailbox, _, _ = browser_site
    page = browser.new_page()
    page.goto(url + "/?login=1")
    assert page.get_by_label("Sign in as").input_value() == "student"
    assert page.get_by_label("Sign in as").locator("option").all_text_contents() == [
        "Student",
        "Admin",
    ]
    page.locator("#login-form").get_by_role("button", name="Forgot password?").click()
    page.get_by_role("heading", name="Forgot your password?").wait_for()
    page.get_by_label("Email address").fill("partner@dut4life.ac.za")
    page.get_by_role("button", name="Send reset code").click()
    page.get_by_role("heading", name="Choose a new password.").wait_for()
    code = re.search(
        r"code is: ([0-9]{6})", mailbox[-1].get_body(preferencelist=("plain",)).get_content()
    ).group(1)
    page.get_by_label("Reset code", exact=True).fill(code)
    page.get_by_label("New password").fill("RecoveredStudentPassword123")
    page.get_by_label("Confirm password").fill("RecoveredStudentPassword123")
    page.get_by_role("button", name="Reset password", exact=True).click()
    page.locator("#login-form").wait_for()
    page.get_by_label("Email address").fill("partner@dut4life.ac.za")
    page.get_by_label("Password", exact=True).fill("RecoveredStudentPassword123")
    page.locator("#login-form").get_by_role("button", name="Sign in", exact=True).click()
    page.get_by_role("heading", name="People to learn with").wait_for()
    page.close()
