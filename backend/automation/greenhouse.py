"""Greenhouse form inspection and deterministic profile-based filling."""

import os
import re
from dataclasses import dataclass, field
from datetime import date

from playwright.sync_api import Error as PlaywrightError


class AutomationError(Exception):
    """A user-facing automation failure."""


MANUAL_APPLY_PATTERN = re.compile(
    r"^(apply( for this job| now)?|apply for this position)$", re.IGNORECASE
)

INSPECT_SCRIPT = """
() => {
  const selector = 'input, select, textarea';
  const controls = Array.from(document.querySelectorAll(selector));
  return controls.map((el, index) => {
    const key = 'agent-' + index;
    el.setAttribute('data-agent-key', key);

    const labels = el.labels ? Array.from(el.labels).map(l => l.innerText) : [];
    const container = el.closest(
      '.field-wrapper, .field, .question, fieldset, .application-question'
    );
    const directLabel = container
      ? Array.from(container.children).find(
          child => child.tagName === 'LEGEND' || child.tagName === 'LABEL'
        )
      : null;
    const containerText = directLabel
      ? directLabel.innerText
      : (container ? container.innerText : '');
    const group = el.closest('[role="group"]');
    const groupLabelId = group ? group.getAttribute('aria-labelledby') : '';
    const groupLabel = groupLabelId
      ? ((document.getElementById(groupLabelId) || {}).innerText || '')
      : '';
    const ownLabel =
      labels[0] || el.getAttribute('aria-label') || el.getAttribute('placeholder') || '';
    const rawLabel = (
      el.type === 'file' && groupLabel ? groupLabel : ownLabel
    ).trim();

    const required =
      el.required ||
      el.getAttribute('aria-required') === 'true' ||
      (group && group.getAttribute('aria-required') === 'true') ||
      containerText.includes('*') ||
      rawLabel.includes('*');

    const rect = el.getBoundingClientRect();
    const style = window.getComputedStyle(el);
    const hiddenByClass = (el.className && String(el.className).includes('visually-hidden'));
    const visible =
      el.type === 'file' ||
      (!hiddenByClass && rect.width > 0 && rect.height > 0 &&
       style.visibility !== 'hidden' && style.display !== 'none');

    const options = el.tagName === 'SELECT'
      ? Array.from(el.options).map(o => ({ value: o.value, text: o.textContent.trim() }))
      : [];

    return {
      key,
      tag: el.tagName.toLowerCase(),
      type: (el.getAttribute('type') || '').toLowerCase(),
      role: el.getAttribute('role') || '',
      id: el.id || '',
      name: el.name || '',
      label: rawLabel.replace(/\\s+/g, ' ').replace(/\\*/g, '').trim(),
      question: containerText.replace(/\\s+/g, ' ').replace(/\\*/g, '').trim(),
      required,
      visible,
      disabled: !!el.disabled,
      tabIndex: el.tabIndex,
      ariaHidden: el.getAttribute('aria-hidden') === 'true',
      value: typeof el.value === 'string' ? el.value : '',
      checked: !!el.checked,
      fileCount: el.files ? el.files.length : 0,
      options,
    };
  });
}
"""

META_SCRIPT = """
() => {
  const pick = (selector) => {
    const el = document.querySelector(selector);
    return el ? el.innerText.trim() : '';
  };
  const meta = (property) => {
    const el = document.querySelector(`meta[property="${property}"]`);
    return el ? el.getAttribute('content') || '' : '';
  };
  return {
    title: document.title || '',
    h1: pick('h1'),
    company:
      pick('.company-name') ||
      pick('[data-company]') ||
      meta('og:site_name') ||
      '',
  };
}
"""


@dataclass
class FillResult:
    filled: list[tuple[str, str]] = field(default_factory=list)
    review_items: list[dict] = field(default_factory=list)
    inspected: int = 0
    required: int = 0
    ai_filled: list[dict] = field(default_factory=list)
    ai_errors: list[str] = field(default_factory=list)


def normalize(value):
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


def _contains_word(text, *terms):
    """Match whole words/phrases, never fragments such as city in ethnicity."""
    for term in terms:
        if re.search(rf"\b{re.escape(term)}\b", text or ""):
            return True
    return False


def _control_text(control, keys=("label", "question", "name", "id")):
    return normalize(
        " ".join(str(control.get(key) or "") for key in keys)
    )


def _control_label(control):
    """Use only the visible label for short factual fields.

    Long legal/policy paragraphs often contain words such as "state" or "city"
    incidentally. Derivation must never treat those paragraphs as short fields.
    """
    label = normalize(control.get("label") or "")
    if label:
        return label
    question = normalize(control.get("question") or "")
    return question if len(question) <= 120 else ""


def has_greenhouse_form(page):
    try:
        return page.evaluate(
            """() => {
                const visible = (el) => {
                    if (!el) return false;
                    const rect = el.getBoundingClientRect();
                    const style = getComputedStyle(el);
                    return rect.width > 0 && rect.height > 0 &&
                        style.visibility !== 'hidden' && style.display !== 'none' &&
                        style.opacity !== '0';
                };
                const form = document.querySelector('#application-form, #application_form');
                if (visible(form)) return true;
                return visible(
                    document.querySelector('#first_name, input[name="first_name"]')
                );
            }"""
        )
    except PlaywrightError:
        return False


def wait_for_form(page, timeout_ms=15000):
    elapsed = 0
    step = 500
    while elapsed <= timeout_ms:
        if has_greenhouse_form(page):
            return True
        page.wait_for_timeout(step)
        elapsed += step
    return False


def reveal_form_if_needed(page):
    """Click an Apply button only when the form is not already on the page."""
    if has_greenhouse_form(page):
        return

    candidates = [
        page.get_by_role("button", name=MANUAL_APPLY_PATTERN),
        page.get_by_role("link", name=MANUAL_APPLY_PATTERN),
    ]
    for candidate in candidates:
        try:
            button = candidate.first
            if button.count() and button.is_visible():
                button.click()
                page.wait_for_timeout(1500)
                return
        except PlaywrightError:
            continue


def read_job_meta(page):
    try:
        meta = page.evaluate(META_SCRIPT)
    except PlaywrightError:
        return "", ""

    title = meta.get("title", "")
    role = meta.get("h1", "")
    company = meta.get("company", "")

    if not role and title:
        role = re.split(r"\s+(?:at|@)\s+", title, maxsplit=1)[0].strip()
    if not company and title:
        match = re.search(
            r"\s+(?:at|@)\s+(.+?)(?:\s*[|\-–]\s*.*)?$", title, re.IGNORECASE
        )
        if match:
            company = match.group(1).strip()
    return company[:255], role[:255]


def inspect_fields(page):
    try:
        return page.evaluate(INSPECT_SCRIPT)
    except PlaywrightError as exc:
        raise AutomationError(f"Could not inspect the form: {exc}") from exc


LOGIN_SCRIPT = """
() => {
  if (document.querySelector('#application-form, #application_form')) {
    const form = document.querySelector('#application-form, #application_form');
    const rect = form.getBoundingClientRect();
    if (rect.width > 0 && rect.height > 0) return false;
  }
  const path = location.pathname.toLowerCase();
  const urlMatch = /(sign[_-]?in|log[_-]?in|auth|verify|security[_-]?code)/.test(path);
  const visibleInputs = Array.from(
    document.querySelectorAll('input[type="email"], input[type="password"], input[autocomplete="one-time-code"]')
  ).filter((el) => {
    const rect = el.getBoundingClientRect();
    const style = getComputedStyle(el);
    return rect.width > 0 && rect.height > 0 &&
      style.visibility !== 'hidden' && style.display !== 'none';
  });
  const text = document.body ? document.body.innerText : '';
  const textMatch = /sign in to (continue|apply)|verify your email|enter the (verification|security) code|check your email/i.test(text);
  return urlMatch || (visibleInputs.length > 0 && textMatch);
}
"""


def is_login_wall(page):
    try:
        return bool(page.evaluate(LOGIN_SCRIPT))
    except PlaywrightError:
        return False


SUBMISSION_SIGNAL_SCRIPT = """
() => {
  const visible = (el) => {
    if (!el) return false;
    const rect = el.getBoundingClientRect();
    const style = getComputedStyle(el);
    return rect.width > 0 && rect.height > 0 &&
      style.visibility !== 'hidden' && style.display !== 'none' &&
      style.opacity !== '0';
  };
  const bodyText = document.body ? document.body.innerText || '' : '';
  const url = location.href;
  const form = document.querySelector('#application-form, #application_form');
  const formVisible = visible(form);

  const successPatterns = [
    /thank you for applying/i,
    /your application (?:has been|was) (?:received|submitted)/i,
    /we(?:'| ha)ve received your application/i,
    /application submitted successfully/i,
    /thanks for applying/i,
  ];
  const pathIsConfirmation = /\\/confirmation(?:[/?#]|$)/i.test(location.pathname + location.search + location.hash);
  const matched = successPatterns
    .map((pattern) => bodyText.match(pattern))
    .find(Boolean);
  if (pathIsConfirmation || (matched && !formVisible)) {
    const index = matched ? Math.max(0, bodyText.indexOf(matched[0]) - 160) : 0;
    return {
      kind: 'confirmed',
      signal: pathIsConfirmation ? 'url' : 'message',
      url,
      message: bodyText.slice(index, index + 600).replace(/\\s+/g, ' ').trim(),
    };
  }

  const challenge = document.querySelector(
    'iframe[src*="recaptcha"][src*="bframe"], ' +
    'iframe[title*="challenge" i], #rc-imageselect, .rc-imageselect'
  );
  const checkText = bodyText;
  if (visible(challenge) || /verify you are human|i'm not a robot|select all (images|squares)/i.test(checkText)) {
    return { kind: 'captcha', url };
  }

  if (/sign in to (continue|apply)|verify your email|enter the (verification|security) code/i.test(checkText) &&
      !formVisible) {
    return { kind: 'login', url };
  }

  return { kind: 'none', url };
}
"""


def wait_for_submission_signal(page, timeout_ms=30000):
    """Return confirmed/captcha/login/none without treating a click as success."""
    elapsed = 0
    step = 500
    last = {"kind": "none"}
    while elapsed <= timeout_ms:
        if page.is_closed():
            return last
        try:
            last = page.evaluate(SUBMISSION_SIGNAL_SCRIPT)
        except PlaywrightError:
            last = {"kind": "none"}
        if last.get("kind") in ("confirmed", "captcha", "login"):
            return last
        page.wait_for_timeout(step)
        elapsed += step
    return last


def wait_for_confirmation(page, timeout_ms=30000):
    """Wait only for a verified confirmation, ignoring captcha/login prompts."""
    elapsed = 0
    step = 500
    while elapsed <= timeout_ms:
        if page.is_closed():
            return None
        try:
            signal = page.evaluate(SUBMISSION_SIGNAL_SCRIPT)
        except PlaywrightError:
            signal = {"kind": "none"}
        if signal.get("kind") == "confirmed":
            return signal
        page.wait_for_timeout(step)
        elapsed += step
    return None


def has_captcha_challenge(page):
    try:
        signal = page.evaluate(SUBMISSION_SIGNAL_SCRIPT)
        return signal.get("kind") == "captcha"
    except PlaywrightError:
        return False


def find_submit_button(page):
    selectors = (
        '#application-form button[type="submit"]',
        '#application_form button[type="submit"]',
        'form button[type="submit"]',
        'button:has-text("Submit application")',
        'input[type="submit"][value*="Submit" i]',
    )
    for selector in selectors:
        locator = page.locator(selector)
        try:
            count = locator.count()
        except PlaywrightError:
            continue
        for index in range(min(count, 5)):
            candidate = locator.nth(index)
            try:
                if candidate.is_visible() and candidate.is_enabled():
                    return candidate
            except PlaywrightError:
                continue
    return None


def collect_submission_errors(page):
    try:
        return page.evaluate(
            """() => {
                const visible = (el) => {
                    if (!el) return false;
                    const rect = el.getBoundingClientRect();
                    const style = getComputedStyle(el);
                    return rect.width > 0 && rect.height > 0 &&
                        style.visibility !== 'hidden' && style.display !== 'none';
                };
                const messages = [];
                const add = (value) => {
                    const text = (value || '').replace(/\\s+/g, ' ').trim();
                    if (text && !messages.includes(text)) messages.push(text.slice(0, 300));
                };
                document.querySelectorAll(
                    '[role="alert"], .field-error, .error-message, .application--error'
                ).forEach((el) => {
                    if (visible(el)) add(el.innerText);
                });
                document.querySelectorAll(
                    '#application-form [aria-invalid="true"], #application_form [aria-invalid="true"]'
                ).forEach((el) => {
                    if (!visible(el)) return;
                    const container = el.closest('.field-wrapper, .field, .question, fieldset');
                    const label = container
                        ? (container.innerText || '').replace(/\\s+/g, ' ').trim()
                        : '';
                    add(label || el.getAttribute('aria-label') || el.name || 'Invalid field');
                });
                return messages.slice(0, 5);
            }"""
        )
    except PlaywrightError:
        return []


def click_submit(page):
    # Greenhouse boards sometimes show a cookie banner over the submit button.
    for name in ("Ok", "Accept", "Accept all", "I agree"):
        try:
            button = page.get_by_role("button", name=name, exact=True)
            if button.count() and button.first.is_visible():
                button.first.click()
                page.wait_for_timeout(200)
                break
        except PlaywrightError:
            continue

    button = find_submit_button(page)
    if button is None:
        raise AutomationError(
            "The application form is complete, but no enabled Submit button was found."
        )
    try:
        button.scroll_into_view_if_needed()
        button.click()
    except PlaywrightError as exc:
        raise AutomationError(f"Could not click the Submit button: {exc}") from exc
    return button.inner_text().strip() or "Submit"


def _is_fillable(control):
    if control.get("disabled") or control.get("ariaHidden"):
        return False
    if control.get("tabIndex", 0) < 0 and control.get("type") != "file":
        return False
    return control.get("visible", True) or control.get("type") == "file"


def _standard_key(control):
    ident = normalize(f"{control.get('id', '')} {control.get('name', '')}")
    label = normalize(control.get("label", ""))

    # Never reuse the legal first name for a preferred-name field.
    if "preferred" in label and "name" in label:
        return ""

    if "first name" in label or "first name" in ident or "firstname" in ident:
        return "first_name"
    if "last name" in label or "last name" in ident or "lastname" in ident:
        return "last_name"
    if "email" in label or "e mail" in label or "email" in ident:
        return "email"
    if (
        label in ("phone", "phone number", "mobile", "mobile phone")
        or "phone" in label
        or "phone" in ident
    ):
        return "phone"
    if "linkedin" in label or "linkedin" in ident:
        return "linkedin"
    if "github" in label or "github" in ident:
        return "github"
    if "website" in label or "portfolio" in label or "website" in ident:
        return "website"
    if (
        "location" in label
        or "city" in label
        or "candidate location" in ident
        or "job application location" in ident
    ):
        return "location"
    if "country" in label or "country" in ident:
        return "country"
    return ""


def _profile_value(profile, key):
    personal = profile.get("personal", {})
    full_name = (personal.get("full_name") or "").strip()
    parts = full_name.split()

    if key == "first_name":
        return (personal.get("first_name") or (parts[0] if parts else "")).strip()
    if key == "last_name":
        return (
            personal.get("last_name")
            or (" ".join(parts[1:]) if len(parts) > 1 else "")
        ).strip()
    if key == "email":
        return (personal.get("email") or "").strip()
    if key == "phone":
        return (personal.get("phone") or "").strip()
    if key == "location":
        return (personal.get("location") or "").strip()
    if key == "country":
        return (personal.get("country") or "").strip()
    if key == "linkedin":
        return (personal.get("linkedin_url") or "").strip()
    if key == "github":
        return (personal.get("github_url") or "").strip()
    if key == "website":
        return (personal.get("website_url") or "").strip()
    return ""


def get_degree_level(degree_name):
    """Normalize a degree string into a standard education level."""
    d = normalize(str(degree_name or ""))
    if not d:
        return ""
    if any(
        term in d
        for term in (
            "b tech", "btech", "b e", "be", "b s", "bs", "bsc", "b sc",
            "b a", "ba", "bca", "b bachelor", "bachelor", "bachelors",
            "undergraduate", "four year", "4 year", "four year degree",
            "4 year degree", "bachelor of technology", "bachelor of engineering",
            "bachelor of science", "bachelor of arts",
        )
    ):
        return "bachelor"
    if any(
        term in d
        for term in (
            "m tech", "mtech", "m e", "me", "m s", "ms", "msc", "m sc",
            "m a", "ma", "mca", "mba", "master", "masters", "postgraduate",
            "graduate degree", "master of technology", "master of engineering",
            "master of science", "master of business",
        )
    ):
        return "master"
    if any(
        term in d
        for term in (
            "phd", "ph d", "doctorate", "doctoral", "doctor of philosophy"
        )
    ):
        return "doctorate"
    if any(
        term in d
        for term in ("associate", "associates", "2 year", "two year")
    ):
        return "associate"
    if any(
        term in d
        for term in ("high school", "secondary", "ged", "12th", "diploma")
    ):
        return "high_school"
    return "other"


def is_degree_control(control):
    text = normalize(
        " ".join(
            str(control.get(key) or "")
            for key in ("label", "question", "name", "id")
        )
    )
    return any(
        term in text
        for term in (
            "degree",
            "qualification",
            "education level",
            "highest education",
            "level of education",
            "highest degree",
        )
    ) and not any(
        term in text
        for term in ("field of study", "major", "school", "institution", "university", "college")
    )


def is_school_control(control):
    text = normalize(
        " ".join(
            str(control.get(key) or "")
            for key in ("label", "question", "name", "id")
        )
    )
    return any(
        term in text
        for term in (
            "school",
            "university",
            "college",
            "institution",
            "alma mater",
            "institute",
        )
    ) and not any(
        term in text
        for term in ("high school", "law school", "medical school", "field of study", "degree", "major")
    )


def is_discipline_control(control):
    text = _control_text(control)
    return any(
        term in text
        for term in (
            "discipline",
            "field of study",
            "area of study",
            "major",
            "concentration",
        )
    ) and not any(
        term in text
        for term in (
            "degree",
            "school",
            "university",
            "college",
            "institution",
            "gpa",
            "graduation",
        )
    )


def find_best_text_option(candidate, options):
    """Match a free-text profile fact to an option by exact or contained text."""
    if not candidate or not options:
        return None
    candidate = str(candidate).strip()
    for option in options:
        text = str(
            option.get("text") or option.get("value") or ""
            if isinstance(option, dict)
            else option
        ).strip()
        if _option_matches(text, candidate):
            return option
    return None


def find_best_degree_option(candidate_degree, options):
    """Match candidate degree to available options, equivalent levels, or 'Other'."""
    if not candidate_degree or not options:
        return None

    def opt_info(o):
        text = str(
            o.get("text") or o.get("value") or "" if isinstance(o, dict) else o
        ).strip()
        return text, normalize(text)

    # 1. Direct match
    for opt in options:
        text, _ = opt_info(opt)
        if _option_matches(text, candidate_degree):
            return opt

    level = get_degree_level(candidate_degree)

    if level == "bachelor":
        specific_tech = (
            "bachelor of technology",
            "bachelor of engineering",
            "bachelor of science",
            "b tech",
            "b e",
            "b s",
            "bs",
            "bsc",
            "b eng",
        )
        for opt in options:
            _, norm = opt_info(opt)
            if any(term == norm or norm.startswith(term + " ") for term in specific_tech):
                return opt

        generic_bachelor = (
            "bachelor s degree",
            "bachelor s",
            "bachelors degree",
            "bachelors",
            "bachelor",
            "undergraduate degree",
            "undergraduate",
            "four year degree",
            "4 year degree",
            "college degree",
            "four year college",
        )
        for opt in options:
            _, norm = opt_info(opt)
            if any(
                term == norm or norm.startswith(term + " ") or term in norm
                for term in generic_bachelor
            ):
                return opt

    elif level == "master":
        specific_master = (
            "master of technology",
            "master of engineering",
            "master of science",
            "m tech",
            "m e",
            "m s",
            "ms",
            "msc",
            "mca",
            "mba",
        )
        for opt in options:
            _, norm = opt_info(opt)
            if any(term == norm or norm.startswith(term + " ") for term in specific_master):
                return opt

        generic_master = (
            "master s degree",
            "master s",
            "masters degree",
            "masters",
            "master",
            "graduate degree",
            "postgraduate",
        )
        for opt in options:
            _, norm = opt_info(opt)
            if any(
                term == norm or norm.startswith(term + " ") or term in norm
                for term in generic_master
            ):
                return opt

    elif level == "doctorate":
        doc_patterns = ("doctorate", "ph d", "phd", "doctoral", "doctor of philosophy")
        for opt in options:
            _, norm = opt_info(opt)
            if any(term in norm for term in doc_patterns):
                return opt

    elif level == "associate":
        assoc_patterns = ("associate", "associate s", "associates", "2 year", "two year")
        for opt in options:
            _, norm = opt_info(opt)
            if any(term in norm for term in assoc_patterns):
                return opt

    # 4. Fallback: 'Other' / 'Not Listed'
    other_patterns = (
        "other",
        "other degree",
        "not listed",
        "degree not listed",
        "unlisted",
        "none of the above",
    )
    for opt in options:
        _, norm = opt_info(opt)
        if norm in other_patterns or norm.startswith("other ") or norm == "other":
            return opt

    return None


def find_best_school_option(candidate_school, options):
    """Match candidate school to available options, stripped name, or 'Other'."""
    if not candidate_school or not options:
        return None

    def opt_info(o):
        text = str(
            o.get("text") or o.get("value") or "" if isinstance(o, dict) else o
        ).strip()
        return text, normalize(text)

    # 1. Exact or direct match
    for opt in options:
        text, _ = opt_info(opt)
        if _option_matches(text, candidate_school):
            return opt

    # 2. Try school name without location/city suffix (e.g. without ", Indore")
    parts = re.split(r"[,–—|-]", candidate_school)
    if len(parts) > 1:
        core_name = parts[0].strip()
        if len(core_name) >= 4:
            for opt in options:
                text, _ = opt_info(opt)
                if _option_matches(text, core_name):
                    return opt

    # 3. Fallback to 'Other' / 'Not Listed' option
    other_patterns = (
        "other",
        "other not listed",
        "not listed",
        "school not listed",
        "college not listed",
        "university not listed",
        "institution not listed",
        "unlisted",
        "i do not see my school",
        "not in list",
        "other institution",
        "other school",
        "other university",
        "other college",
        "none of the above",
    )
    for opt in options:
        _, norm = opt_info(opt)
        if norm in other_patterns:
            return opt

    for opt in options:
        _, norm = opt_info(opt)
        if (
            norm.startswith("other ")
            or norm.startswith("other/")
            or "not listed" in norm
            or norm == "other"
        ):
            return opt

    return None


def find_other_school_option(options):
    """Locate an 'Other' / 'Not Listed' option in a list of options."""
    for option in options or []:
        opt_text = str(
            option.get("text") or option.get("value") or ""
            if isinstance(option, dict)
            else option
        )
        norm = normalize(opt_text)
        if norm in (
            "other",
            "other not listed",
            "not listed",
            "school not listed",
            "college not listed",
            "university not listed",
            "institution not listed",
            "unlisted",
            "i do not see my school",
            "not in list",
            "other institution",
            "other school",
            "other university",
            "other college",
            "none of the above",
        ):
            return option
    for option in options or []:
        opt_text = str(
            option.get("text") or option.get("value") or ""
            if isinstance(option, dict)
            else option
        )
        norm = normalize(opt_text)
        if (
            norm.startswith("other ")
            or norm.startswith("other/")
            or "not listed" in norm
            or norm == "other"
        ):
            return option
    return None


def _education_value(profile, control):
    """Return an explicitly saved education fact for a clearly labeled field."""
    education = [
        item for item in (profile.get("education") or []) if isinstance(item, dict)
    ]
    if not education:
        return ""

    item = education[0]
    question = normalize(
        " ".join(
            str(control.get(key) or "")
            for key in ("label", "question", "name", "id")
        )
    )
    if not question:
        return ""

    dates = str(item.get("dates") or "").strip()
    date_range = re.split(r"\s+(?:-|–|—|to)\s+", dates, maxsplit=1, flags=re.I)
    start_date = str(item.get("start_date") or "").strip()
    end_date = str(
        item.get("end_date")
        or item.get("graduation_date")
        or item.get("expected_graduation_date")
        or ""
    ).strip()
    if not start_date and len(date_range) == 2:
        start_date = date_range[0].strip()
    if not end_date and len(date_range) == 2:
        end_date = date_range[1].strip()

    end_text = f"{end_date} {date_range[1] if len(date_range) == 2 else dates}".strip()

    if any(
        term in question
        for term in ("graduation year", "year of graduation", "grad year", "degree year")
    ):
        years = re.findall(r"\b(20\d{2})\b", end_text or dates)
        if years:
            return years[-1]

    if any(
        term in question
        for term in ("graduation month", "month of graduation", "grad month")
    ):
        months = [
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December"
        ]
        target = end_text.lower()
        for m in months:
            if m.lower() in target or m[:3].lower() in target:
                return m

    if any(term in question for term in ("graduation", "expected to graduate")):
        return end_date
    if any(term in question for term in ("start date", "enrollment date", "from date")):
        return start_date
    if any(term in question for term in ("end date", "completion date", "to date")):
        return end_date
    if any(term in question for term in ("dates attended", "attendance dates")):
        return dates or " - ".join(
            value for value in (start_date, end_date) if value
        )

    field_name = ""
    if any(term in question for term in ("gpa", "grade point average")):
        field_name = "gpa"
    elif any(
        term in question
        for term in (
            "field of study",
            "area of study",
            "major",
            "discipline",
            "concentration",
        )
    ):
        field_name = "field_of_study"
    elif any(term in question for term in ("degree", "qualification")):
        field_name = "degree"
    elif any(
        term in question
        for term in (
            "school",
            "university",
            "college",
            "institution",
        )
    ):
        field_name = "institution"

    if field_name:
        aliases = {
            "institution": ("institution", "school", "university", "college"),
            "degree": ("degree", "qualification"),
            "field_of_study": ("field_of_study", "field", "major"),
            "gpa": ("gpa",),
        }
        for key in aliases[field_name]:
            value = item.get(key)
            if value:
                raw_val = str(value).strip()
                options = control.get("options") or []
                if options:
                    if field_name == "degree":
                        matched = find_best_degree_option(raw_val, options)
                        if matched:
                            return str(
                                matched.get("text") or matched.get("value") or ""
                                if isinstance(matched, dict)
                                else matched
                            )
                    elif field_name == "institution":
                        matched = find_best_school_option(raw_val, options)
                        if matched:
                            return str(
                                matched.get("text") or matched.get("value") or ""
                                if isinstance(matched, dict)
                                else matched
                            )
                    elif field_name == "field_of_study":
                        matched = find_best_text_option(raw_val, options)
                        if matched:
                            return str(
                                matched.get("text") or matched.get("value") or ""
                                if isinstance(matched, dict)
                                else matched
                            )
                return raw_val
        return ""

    return ""


def _work_authorization_answer(profile, control):
    """Map only explicitly stated work-authorization facts.

    Country, location, education, and other profile facts are never used to
    infer eligibility. Citizenship, security clearance, legal attestations,
    and demographic questions always require an explicit saved answer.
    """
    text = _control_text(control)
    if not text:
        return ""

    # These must never be answered from the free-text work-authorization field.
    if _contains_word(
        text,
        "citizen",
        "citizenship",
        "permanent resident",
        "green card",
        "lawful permanent",
        "security clearance",
        "clearance",
        "affirmation",
        "acknowledgement",
        "acknowledgment",
        "arbitration",
        "at will",
        "consent",
        "signature",
        "certify",
        "attest",
        "background check",
        "criminal",
        "drug test",
        "date of birth",
        "gender",
        "race",
        "ethnicity",
        "veteran",
        "disability",
        "sexual orientation",
        "home address",
        "mailing address",
        "street address",
    ):
        return ""

    is_sponsorship_q = "sponsorship" in text or (
        "visa" in text and "sponsor" in text
    )
    is_auth_q = any(
        term in text
        for term in (
            "authorized to work",
            "authorised to work",
            "right to work",
            "license to work",
            "licence to work",
            "legal right to work",
            "legally entitled to work",
            "work authorization",
            "work authorisation",
            "work permit",
            "eligible to work",
            "legally eligible",
            "legally authorized",
            "legally authorised",
        )
    )
    if not (is_sponsorship_q or is_auth_q):
        return ""

    fact = str(profile.get("work_authorization") or "").strip()
    if not fact:
        return ""

    fact_text = normalize(fact)
    options = control.get("options") or []
    option_texts = [
        str(option.get("text") or option.get("value") or "")
        if isinstance(option, dict)
        else str(option)
        for option in options
    ]

    us_context = (
        "united states" in text
        or bool(re.search(r"\bu s\b", text))
        or _contains_word(text, "usa")
        or bool(re.search(r"\bin the us\b", text))
    )
    india_context = _contains_word(text, "india")

    answer = ""
    if fact_text in ("yes", "y", "true"):
        answer = "yes"
    elif fact_text in ("no", "n", "false"):
        answer = "no"
    elif is_sponsorship_q:
        requires_phrases = (
            "require sponsorship",
            "requires sponsorship",
            "need sponsorship",
            "needs sponsorship",
            "sponsorship required",
            "will require sponsorship",
            "requires visa sponsorship",
        )
        no_sponsorship_phrases = (
            "do not require sponsorship",
            "does not require sponsorship",
            "not require sponsorship",
            "no sponsorship",
            "no visa sponsorship",
            "without sponsorship",
        )
        requires = any(phrase in fact_text for phrase in requires_phrases)
        no_sponsorship = any(phrase in fact_text for phrase in no_sponsorship_phrases)
        if us_context:
            if no_sponsorship and not requires:
                answer = "no"
            elif requires:
                answer = "yes"
        elif india_context:
            if "outside india" in fact_text:
                answer = "no"
            elif requires and "in india" in fact_text:
                answer = "yes"
            elif no_sponsorship:
                answer = "no"
        elif requires and not no_sponsorship:
            answer = "yes"
        elif no_sponsorship and not requires:
            answer = "no"
    elif is_auth_q:
        not_authorized_phrases = (
            "not authorized to work in the us",
            "not authorised to work in the us",
            "not authorized to work in the usa",
            "not authorised to work in the usa",
            "not authorized to work in the united states",
            "not authorised to work in the united states",
        )
        authorized_us_phrases = (
            "authorized to work in the us",
            "authorised to work in the us",
            "authorized to work in the usa",
            "authorised to work in the usa",
            "authorized to work in the united states",
            "authorised to work in the united states",
            "license to work in the united states",
            "licence to work in the united states",
            "license to work in the us",
            "licence to work in the us",
        )
        not_authorized_india_phrases = (
            "not authorized to work in india",
            "not authorised to work in india",
        )
        authorized_india_phrases = (
            "authorized to work in india",
            "authorised to work in india",
            "eligible to work in india",
            "license to work in india",
            "licence to work in india",
        )
        generic_not_authorized = any(
            phrase in fact_text
            for phrase in (
                "not authorized",
                "not authorised",
                "not eligible to work",
                "not licensed to work",
                "not licenced to work",
                "no work permit",
                "no work license",
                "no work licence",
            )
        )
        generic_authorized = any(
            phrase in fact_text
            for phrase in (
                "authorized to work",
                "authorised to work",
                "eligible to work",
                "licensed to work",
                "licenced to work",
                "have a work permit",
                "hold a work permit",
            )
        )
        if us_context:
            if any(phrase in fact_text for phrase in not_authorized_phrases):
                answer = "no"
            elif requires_us_sponsorship(fact_text):
                answer = "no"
            elif any(phrase in fact_text for phrase in authorized_us_phrases):
                answer = "yes"
        elif india_context:
            if any(phrase in fact_text for phrase in not_authorized_india_phrases):
                answer = "no"
            elif any(phrase in fact_text for phrase in authorized_india_phrases):
                answer = "yes"
        elif generic_not_authorized and not generic_authorized:
            answer = "no"
        elif generic_authorized and not generic_not_authorized:
            answer = "yes"

    if not answer:
        return ""

    for option in option_texts:
        if _option_matches(option, answer):
            return option

    return answer if not option_texts else ""


def requires_us_sponsorship(fact_text):
    """Return True only when the explicit statement requires U.S. sponsorship."""
    if "united states" not in fact_text and not re.search(r"\bin the us\b", fact_text):
        return False
    return any(
        phrase in fact_text
        for phrase in (
            "require sponsorship",
            "requires sponsorship",
            "need sponsorship",
            "needs sponsorship",
            "sponsorship required",
            "will require sponsorship",
            "requires visa sponsorship",
        )
    )


def _find_derived_answer(profile, control):
    """Derive safe answers from short, clearly identified factual fields.

    Only the visible label (or a short question) is inspected. Long legal or
    policy paragraphs are ignored so words such as "state", "city", or
    "citizen" inside them cannot be mistaken for a field label.
    """
    label = _control_label(control)
    if not label:
        return ""

    personal = profile.get("personal") or {}
    education = [
        item for item in (profile.get("education") or []) if isinstance(item, dict)
    ]
    primary_edu = education[0] if education else {}
    dates = str(primary_edu.get("dates") or "").strip()
    date_parts = re.split(r"\s+(?:-|–|—|to)\s+", dates, maxsplit=1, flags=re.I)
    end_date = str(
        primary_edu.get("end_date")
        or primary_edu.get("graduation_date")
        or primary_edu.get("expected_graduation_date")
        or (date_parts[1] if len(date_parts) == 2 else "")
        or ""
    ).strip()
    end_text = f"{end_date} {date_parts[1] if len(date_parts) == 2 else dates}".strip()

    # 1. Graduation year
    if _contains_word(
        label,
        "graduation year",
        "year of graduation",
        "degree year",
        "grad year",
        "completion year",
    ):
        years = re.findall(r"\b(20\d{2})\b", end_text or dates)
        if years:
            return years[-1]

    # 2. Graduation month
    if _contains_word(
        label,
        "graduation month",
        "month of graduation",
        "grad month",
    ):
        months = [
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December"
        ]
        target = end_text.lower()
        for month in months:
            if month.lower() in target or month[:3].lower() in target:
                return month

    # 3. Start year
    if _contains_word(label, "start year", "enrollment year", "from year"):
        start_date = str(primary_edu.get("start_date") or "").strip()
        match = re.search(r"\b(20\d{2})\b", start_date or dates)
        if match:
            return match.group(1)

    # 4. Current student status, derived only from an explicit education end date.
    if _contains_word(
        label,
        "currently enrolled",
        "current student",
        "currently attending",
        "pursuing a degree",
        "are you a student",
        "enrolled in a degree",
    ):
        match = re.search(r"\b(20\d{2})\b", end_text)
        if match:
            return "Yes" if int(match.group(1)) >= date.today().year else "No"
        return ""

    # 5. State / Province. Only a short label or a name/id may trigger this.
    short_label = label if len(label) <= 60 else ""
    identity = f"{short_label} {_control_text(control, keys=('name', 'id'))}".strip()
    if _contains_word(identity, "state", "province") and not _contains_word(
        identity, "statement", "status", "united states"
    ):
        parts = [part.strip() for part in (personal.get("location") or "").split(",") if part.strip()]
        if len(parts) >= 2:
            return parts[1]
        if len(parts) == 1:
            return parts[0]

    # 6. City / town, using whole words so "ethnicity" never matches "city".
    if _contains_word(identity, "city", "town"):
        parts = [part.strip() for part in (personal.get("location") or "").split(",") if part.strip()]
        if parts:
            return parts[0]

    # 7. Degree level / Highest level of education
    if _contains_word(
        label,
        "highest level of education",
        "highest education",
        "education level",
        "degree level",
    ):
        degree = primary_edu.get("degree") or ""
        level = get_degree_level(degree)
        if level == "bachelor":
            return "Bachelor's Degree"
        if level == "master":
            return "Master's Degree"
        if level == "doctorate":
            return "Doctorate"
        if level == "associate":
            return "Associate's Degree"
        if level == "high_school":
            return "High School Diploma"

    return ""


def _find_answer_in(mapping, *texts):
    for text in texts:
        wanted = normalize(text)
        if not wanted:
            continue
        for key, value in (mapping or {}).items():
            normalized_key = normalize(key)
            if not normalized_key or not value:
                continue
            if normalized_key == wanted:
                return value
            if len(normalized_key) >= 10 and (
                normalized_key in wanted or wanted in normalized_key
            ):
                return value
    return ""


def _find_saved_answer(profile, *texts):
    return _find_answer_in(profile.get("saved_answers", {}), *texts)


def _find_resolved_answer(resolved_answers, *texts):
    return _find_answer_in(resolved_answers or {}, *texts)


def _option_matches(option_text, answer):
    option = normalize(option_text)
    wanted = normalize(answer)
    if not option or not wanted:
        return False
    if option == wanted:
        return True
    if len(wanted) >= 3 and (wanted in option or option in wanted):
        return True
    # Simple yes/no confirmation
    yes = {"yes", "y", "true"}
    no = {"no", "n", "false"}
    return (wanted in yes and option in yes) or (wanted in no and option in no)


def _label_for(control):
    return control.get("label") or control.get("question") or control.get("name") or "field"


def _fill_text(page, control, value):
    locator = page.locator(f'[data-agent-key="{control["key"]}"]')
    locator.fill(str(value))


def _fill_native_select(page, control, answer):
    locator = page.locator(f'[data-agent-key="{control["key"]}"]')
    options = control.get("options", [])

    # 1. Direct match
    for option in options:
        if _option_matches(option.get("text", ""), answer) or _option_matches(
            option.get("value", ""), answer
        ):
            locator.select_option(value=option["value"])
            return True

    # 2. Equivalent degree options
    if is_degree_control(control):
        best = find_best_degree_option(answer, options)
        if best:
            locator.select_option(value=best["value"])
            return True

    # 3. School options, including "Other / Not Listed"
    if is_school_control(control):
        best = find_best_school_option(answer, options)
        if best:
            locator.select_option(value=best["value"])
            return True

    # 4. Field-of-study / discipline option matching
    if is_discipline_control(control):
        best = find_best_text_option(answer, options)
        if best:
            locator.select_option(value=best["value"])
            return True

    return False


def _visible_options(page):
    return page.locator('[role="option"]:visible')


def _wait_for_options(page, timeout_ms=2000):
    """Wait for a React-select option list instead of assuming a fixed delay."""
    elapsed = 0
    step = 100
    while elapsed <= timeout_ms:
        options = _visible_options(page)
        if options.count() > 0:
            return options
        page.wait_for_timeout(step)
        elapsed += step
    return _visible_options(page)


def _click_matching_option(options, query):
    """Click the best visible option for a query; never pick an unrelated one."""
    wanted = normalize(query)
    if not wanted:
        return False

    candidates = []
    for index in range(options.count()):
        try:
            text = options.nth(index).inner_text().strip()
        except PlaywrightError:
            continue
        if text:
            candidates.append((index, normalize(text)))

    predicates = (
        lambda option: option == wanted,
        lambda option: option.startswith(wanted + " "),
        lambda option: f" {wanted} " in f" {option} ",
    )
    for predicate in predicates:
        for index, option_text in candidates:
            if predicate(option_text):
                try:
                    options.nth(index).click()
                    return True
                except PlaywrightError:
                    continue
    return False


def _fill_combobox(page, control, answer):
    """Handle React-select style comboboxes used by modern Greenhouse forms."""
    locator = page.locator(f'[data-agent-key="{control["key"]}"]')
    try:
        locator.click()
        try:
            locator.fill(str(answer))
        except PlaywrightError:
            # Some combobox inputs are read-only; type instead of fill.
            page.keyboard.type(str(answer))

        options = _wait_for_options(page)
        if _click_matching_option(options, answer):
            page.wait_for_timeout(150)
            return True

        fallback_queries = []
        if is_degree_control(control):
            level = get_degree_level(answer)
            if level == "bachelor":
                fallback_queries = [
                    "Bachelor's Degree", "Bachelor's", "Bachelors",
                    "Bachelor of Engineering", "Bachelor of Science",
                    "Undergraduate", "Other",
                ]
            elif level == "master":
                fallback_queries = [
                    "Master's Degree", "Master's", "Masters",
                    "Master of Technology", "Master of Science", "Other",
                ]
            else:
                fallback_queries = ["Other"]
        elif is_school_control(control):
            parts = re.split(r"[,–—|-]", str(answer))
            if len(parts) > 1 and len(parts[0].strip()) >= 4:
                fallback_queries.append(parts[0].strip())
            fallback_queries.extend(["Other", "Not Listed", "Other / Not Listed"])
        elif is_discipline_control(control):
            parts = re.split(r"[,/]| and ", str(answer))
            fallback_queries.extend(
                part.strip()
                for part in parts
                if part.strip() and part.strip() != str(answer).strip()
            )

        for query in fallback_queries:
            if normalize(query) == normalize(answer):
                continue
            try:
                locator.click()
                try:
                    locator.fill("")
                    locator.fill(query)
                except PlaywrightError:
                    page.keyboard.press("Control+A")
                    page.keyboard.type(query)
                options = _wait_for_options(page)
                if _click_matching_option(options, query):
                    page.wait_for_timeout(150)
                    return True
            except PlaywrightError:
                continue

        page.keyboard.press("Escape")
        return False
    except PlaywrightError:
        return False


def _upload_file(page, control, path):
    page.locator(f'[data-agent-key="{control["key"]}"]').set_input_files(path)


def fill_application(page, profile, resolved_answers=None, ai_mapper=None):
    controls = [control for control in inspect_fields(page) if _is_fillable(control)]
    result = FillResult(inspected=len(controls))
    result.required = len([c for c in controls if c.get("required")])
    resolved_answers = resolved_answers or {}

    resume_path = (profile.get("resume_path") or "").strip()
    if resume_path and not os.path.isfile(resume_path):
        resume_path = ""

    cover_letter_path = (profile.get("cover_letter_path") or "").strip()
    if cover_letter_path and not os.path.isfile(cover_letter_path):
        cover_letter_path = ""

    reviewed = set()
    radio_groups = {}

    def add_review(name, reason, suggested_value=None, source="deterministic"):
        if name in reviewed:
            return
        reviewed.add(name)
        result.review_items.append(
            {
                "field_name": name,
                "reason": reason,
                "suggested_value": suggested_value,
                "source": source,
            }
        )

    def review(control, reason, suggested_value=None, source="deterministic"):
        add_review(
            _label_for(control),
            reason,
            suggested_value=suggested_value,
            source=source,
        )

    def note_fill(label, value, ai_source=None):
        result.filled.append((label, str(value)))
        if ai_source is not None:
            result.ai_filled.append(
                {
                    "label": label,
                    "value": str(value),
                    "confidence": ai_source.confidence,
                    "reason": ai_source.reason,
                    "matched_profile_key": ai_source.matched_profile_key,
                }
            )

    def ai_suggest(control, question=None, options=None):
        if ai_mapper is None:
            return None
        try:
            suggestion = ai_mapper.suggest(
                control, question=question, options=options
            )
        except Exception as exc:  # AI must never break the automation run.
            result.ai_errors.append(f"{_label_for(control)}: {exc}"[:500])
            return None

        if suggestion.action == "error":
            result.ai_errors.append(
                f"{_label_for(control)}: {suggestion.reason}"[:500]
            )
            return None
        if suggestion.action == "skipped":
            return None
        return suggestion

    def ai_fill_or_review(control, fallback_reason):
        """Try AI for an otherwise-unanswerable required field.

        Returns (answer, ai_source). answer is None when review was recorded.
        """
        suggestion = ai_suggest(control)
        if suggestion is not None and suggestion.action == "fill":
            return suggestion.value, suggestion

        if suggestion is not None and suggestion.action == "review":
            review(
                control,
                suggestion.reason or fallback_reason,
                suggested_value=suggestion.value or None,
                source="ai",
            )
        else:
            review(control, fallback_reason)
        return None, None

    for control in controls:
        field_type = control.get("type", "")
        tag = control.get("tag", "")

        if field_type in ("radio", "checkbox") and control.get("name"):
            group = radio_groups.setdefault(
                control["name"],
                {
                    "question": control.get("question") or control.get("label"),
                    "required": False,
                    "options": [],
                    "controls": [],
                },
            )
            group["required"] = group["required"] or control.get("required")
            group["options"].append(
                {"text": control.get("label", ""), "control": control}
            )
            group["controls"].append(control)
            continue

        if field_type == "file":
            ident = normalize(
                f"{control.get('id', '')} {control.get('name', '')} {control.get('label', '')}"
            )
            question = normalize(
                f"{control.get('label', '')} {control.get('question', '')}"
            )
            if "cover letter" in question:
                if cover_letter_path:
                    try:
                        _upload_file(page, control, cover_letter_path)
                        result.filled.append(
                            (
                                _label_for(control),
                                os.path.basename(cover_letter_path),
                            )
                        )
                        continue
                    except PlaywrightError:
                        review(control, "Cover letter file upload failed.")
                        continue
                if control.get("required"):
                    review(
                        control,
                        "A cover letter file is required, but no valid cover "
                        "letter file is saved in the profile.",
                    )
                continue
            if "resume" in ident or " cv" in f" {ident} " or "resume" in question:
                if resume_path:
                    try:
                        _upload_file(page, control, resume_path)
                        result.filled.append(
                            (_label_for(control), os.path.basename(resume_path))
                        )
                        continue
                    except PlaywrightError:
                        review(control, "Resume upload failed.")
                        continue
                if control.get("required"):
                    review(control, "Resume is required but no valid resume path is saved.")
                continue
            if control.get("required"):
                review(control, "Required file upload is not supported.")
            continue

        standard = _standard_key(control)
        resolved = _find_resolved_answer(
            resolved_answers, control.get("label", ""), control.get("question", "")
        )
        ai_source = None
        if standard:
            answer = _profile_value(profile, standard) or resolved
            if not answer:
                if control.get("required"):
                    review(
                        control,
                        f"Required field is empty in your profile ({_label_for(control)}).",
                    )
                continue
        elif "cover letter" in normalize(control.get("label", "")):
            answer = (profile.get("cover_letter") or "").strip() or resolved
            if not answer:
                if control.get("required"):
                    review(control, "Cover letter is required but not saved in the profile.")
                continue
        else:
            answer = resolved or _find_saved_answer(
                profile, control.get("label", ""), control.get("question", "")
            )
            if not answer:
                answer = _education_value(profile, control)
            if not answer:
                answer = _work_authorization_answer(profile, control)
            if not answer:
                answer = _find_derived_answer(profile, control)
            if not answer:
                if control.get("required"):
                    answer, ai_source = ai_fill_or_review(
                        control,
                        "No approved answer is available in saved answers for this required field.",
                    )
                    if not answer:
                        continue
                else:
                    continue

        try:
            is_combobox = control.get("role") == "combobox"
            if tag == "select":
                if _fill_native_select(page, control, answer):
                    note_fill(_label_for(control), answer, ai_source)
                elif control.get("required"):
                    review(
                        control,
                        "Saved answer does not match any available option.",
                        suggested_value=ai_source.value if ai_source else None,
                        source="ai" if ai_source else "deterministic",
                    )
            elif is_combobox:
                if _fill_combobox(page, control, answer):
                    note_fill(_label_for(control), answer, ai_source)
                elif control.get("required"):
                    review(
                        control,
                        "Could not select the saved answer in the dropdown.",
                        suggested_value=ai_source.value if ai_source else None,
                        source="ai" if ai_source else "deterministic",
                    )
            else:
                _fill_text(page, control, answer)
                note_fill(_label_for(control), answer, ai_source)
        except PlaywrightError:
            if control.get("required"):
                review(
                    control,
                    "The field could not be filled automatically.",
                    suggested_value=ai_source.value if ai_source else None,
                    source="ai" if ai_source else "deterministic",
                )

    for name, group in radio_groups.items():
        question = group["question"] or name
        answer = _find_resolved_answer(resolved_answers, question) or _find_saved_answer(
            profile, question
        )
        if not answer:
            group_control = {
                "label": question,
                "question": question,
                "name": name,
                "type": "radio",
                "required": group["required"],
                "options": [
                    option["text"]
                    for option in group["options"]
                    if option["text"]
                ],
            }
            answer = _work_authorization_answer(profile, group_control)
            if not answer:
                answer = _find_derived_answer(profile, group_control)
        option_texts = [option["text"] for option in group["options"] if option["text"]]
        ai_source = None
        all_radio = all(
            option["control"].get("type") == "radio" for option in group["options"]
        )
        if not answer:
            if group["required"] and all_radio:
                group_control = {
                    "label": question,
                    "question": question,
                    "name": name,
                    "type": "radio",
                    "required": True,
                    "options": option_texts,
                }
                suggestion = ai_suggest(
                    group_control, question=question, options=option_texts
                )
                if suggestion is not None and suggestion.action == "fill":
                    answer = suggestion.value
                    ai_source = suggestion
                elif suggestion is not None and suggestion.action == "review":
                    add_review(
                        question,
                        suggestion.reason
                        or "AI could not confidently answer this required choice.",
                        suggested_value=suggestion.value or None,
                        source="ai",
                    )
                    continue
                else:
                    add_review(
                        question,
                        "No approved answer is available in saved answers for this required field.",
                    )
                    continue
            else:
                if group["required"]:
                    add_review(
                        question,
                        "No approved answer is available in saved answers for this required field.",
                    )
                continue

        matched = False
        for option in group["options"]:
            if _option_matches(option["text"], answer):
                locator = page.locator(
                    f'[data-agent-key="{option["control"]["key"]}"]'
                )
                try:
                    if option["control"].get("type") == "radio":
                        locator.check()
                    else:
                        locator.check()
                    note_fill(question, option["text"], ai_source)
                    matched = True
                except PlaywrightError:
                    pass
                break

        if not matched and group["required"]:
            add_review(
                question,
                "Saved answer does not match any available option ("
                + ", ".join(option_texts)
                + ").",
                suggested_value=ai_source.value if ai_source else None,
                source="ai" if ai_source else "deterministic",
            )

    # Validation pass: required fields that are still empty.
    after = {c["key"]: c for c in inspect_fields(page) if _is_fillable(c)}
    checked_groups = set()
    for control in after.values():
        if not control.get("required"):
            continue

        field_type = control.get("type", "")
        if field_type == "radio":
            group_name = control.get("name")
            if group_name in checked_groups:
                continue
            checked_groups.add(group_name)
            checked = any(
                candidate.get("checked")
                for candidate in after.values()
                if candidate.get("name") == group_name
            )
            if not checked:
                add_review(
                    control.get("question") or _label_for(control),
                    "Required choice was not answered.",
                )
            continue
        if field_type == "checkbox":
            continue
        if field_type == "file":
            if not control.get("fileCount"):
                review(control, "Required file was not uploaded.")
            continue
        if control.get("role") == "combobox":
            # React-select keeps the typed text in the input; trust the fill step.
            continue
        if not (control.get("value") or "").strip():
            review(control, "Required field is still empty after filling.")

    return result
