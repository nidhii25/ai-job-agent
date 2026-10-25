"""Greenhouse form inspection and deterministic profile-based filling."""

import os
import re
from dataclasses import dataclass, field

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


def _education_value(profile, control):
    """Return an explicitly saved education fact for a clearly labeled field."""
    education = [
        item for item in (profile.get("education") or []) if isinstance(item, dict)
    ]
    if len(education) != 1:
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
                return str(value).strip()
        return ""

    return ""


def _work_authorization_answer(profile, control):
    """Map only an explicit work-authorization profile fact to a form answer."""
    question = normalize(
        " ".join(
            str(control.get(key) or "")
            for key in ("label", "question", "name", "id")
        )
    )
    if not question or any(term in question for term in ("citizen", "citizenship")):
        return ""
    if not any(
        term in question
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
            "sponsorship",
        )
    ):
        return ""

    fact = str(profile.get("work_authorization") or "").strip()
    if not fact:
        return ""
    options = control.get("options") or []
    option_texts = [
        str(option.get("text") or option.get("value") or "")
        if isinstance(option, dict)
        else str(option)
        for option in options
    ]
    for option in option_texts:
        if _option_matches(option, fact):
            return option

    fact_text = normalize(fact)
    is_sponsorship_question = "sponsorship" in question
    if is_sponsorship_question:
        if any(
            phrase in fact_text
            for phrase in (
                "require sponsorship",
                "requires sponsorship",
                "need sponsorship",
                "needs sponsorship",
                "sponsorship required",
            )
        ):
            answer = "yes"
        elif any(
            phrase in fact_text
            for phrase in (
                "without sponsorship",
                "no sponsorship",
                "do not require sponsorship",
                "does not require sponsorship",
            )
        ):
            answer = "no"
        else:
            answer = ""
    elif fact_text in ("yes", "y", "true"):
        answer = "yes"
    elif fact_text in ("no", "n", "false"):
        answer = "no"
    elif any(
        phrase in fact_text
        for phrase in (
            "not authorized",
            "not authorised",
            "not eligible",
            "not licensed to work",
            "not licenced to work",
            "no work permit",
            "no work license",
            "no work licence",
            "do not have a license to work",
            "do not have a licence to work",
            "do not hold a work permit",
        )
    ):
        answer = "no"
    elif any(
        phrase in fact_text
        for phrase in (
            "authorized to work",
            "authorised to work",
            "eligible to work",
            "licensed to work",
            "licenced to work",
            "license to work",
            "licence to work",
            "have a work permit",
            "hold a work permit",
        )
    ):
        answer = "yes"
    else:
        answer = ""

    for option in option_texts:
        if _option_matches(option, answer):
            return option
    return answer if not option_texts else ""


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
    for option in control.get("options", []):
        if _option_matches(option.get("text", ""), answer) or _option_matches(
            option.get("value", ""), answer
        ):
            locator.select_option(value=option["value"])
            return True
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
        page.wait_for_timeout(400)

        options = page.locator('[role="option"]:visible')
        count = options.count()
        wanted = normalize(answer)
        candidates = []
        for index in range(count):
            text = options.nth(index).inner_text().strip()
            candidates.append((index, normalize(text)))

        # Prefer exact, then word-prefix, then whole-word containment. Never
        # select an unrelated first option when nothing matches.
        predicates = (
            lambda option: option == wanted,
            lambda option: option.startswith(wanted + " "),
            lambda option: f" {wanted} " in f" {option} ",
        )
        for predicate in predicates:
            for index, option_text in candidates:
                if wanted and predicate(option_text):
                    options.nth(index).click()
                    page.wait_for_timeout(200)
                    return True

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
                else:
                    review(
                        control,
                        "Saved answer does not match any available option.",
                        suggested_value=ai_source.value if ai_source else None,
                        source="ai" if ai_source else "deterministic",
                    )
            elif is_combobox:
                if _fill_combobox(page, control, answer):
                    note_fill(_label_for(control), answer, ai_source)
                else:
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

        if not matched:
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
