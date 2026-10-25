"""Optional Gemini-backed mapping for unfamiliar Greenhouse fields.

The model is only allowed to suggest an answer. Python decides whether that
answer may be typed into the page:

* the field must not be a file upload or a sensitive/eligibility question,
* the answer must be traceable to an explicit profile fact, and
* for option fields, the answer must match one of the options.

Generated prose is returned as a review suggestion by default. It is never
auto-filled unless AI_AUTO_FILL_GENERATED is explicitly enabled.
"""

import json
import logging
import math
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

logger = logging.getLogger("jobagent.ai")

GEMINI_ENDPOINT = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)
DEFAULT_MODEL = "gemini-3.5-flash"

SENSITIVE_PATTERNS = (
    r"\bsalar(?:y|ies)\b",
    r"\bcompensation\b",
    r"\bexpected pay\b",
    r"\bdesired pay\b",
    r"\bpay expectation",
    r"\bwork authori[sz]ation\b",
    r"\bauthori[sz]ed to work\b",
    r"\bright to work\b",
    r"\bsponsor(?:ship)?\b",
    r"\bvisa\b",
    r"\bcitizen(?:ship)?\b",
    r"\bimmigration status\b",
    r"\bgender\b",
    r"\bsex\b",
    r"\brace\b",
    r"\bethnicity\b",
    r"\bracial\b",
    r"\bveteran\b",
    r"\bdisabilit(?:y|ies)\b",
    r"\bsexual orientation\b",
    r"\bdate of birth\b",
    r"\bage\b",
    r"\bsocial security\b",
    r"\bssn\b",
    r"\bgovernment id\b",
    r"\bbackground check\b",
    r"\bcriminal\b",
    r"\bsecurity clearance\b",
    r"\bdrug test\b",
)

PLACEHOLDER_VALUES = {
    "",
    "n a",
    "na",
    "none",
    "null",
    "unknown",
    "not specified",
    "not provided",
    "not applicable",
    "prefer not to say",
    "i don t know",
    "cannot determine",
    "no answer",
}

PROFILE_COLLECTIONS = {"education", "experience", "projects", "skills"}


class AIMapperError(Exception):
    """Raised for configuration or provider failures."""


@dataclass
class AIMapping:
    action: str = "review"  # fill | review | error | skipped
    value: str = ""
    confidence: float = 0.0
    reason: str = ""
    matched_profile_key: str = ""
    answer_kind: str = "none"
    model: str = ""
    raw: dict = field(default_factory=dict)

    @property
    def label(self):
        return self.raw.get("label", "")


def _env_bool(name, default):
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _env_float(name, default):
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_int(name, default):
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def normalize_text(value):
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


def compact_text(value):
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


def is_sensitive_text(value):
    text = normalize_text(value)
    return any(re.search(pattern, text) for pattern in SENSITIVE_PATTERNS)


def is_sensitive_field(control):
    return is_sensitive_text(
        " ".join(
            str(control.get(key) or "")
            for key in ("label", "question", "name", "id")
        )
    )


def _option_texts(options):
    values = []
    for option in options or []:
        if isinstance(option, dict):
            values.append(str(option.get("text") or option.get("value") or ""))
        else:
            values.append(str(option))
    return [value for value in values if value.strip()]


def _option_match(option, value):
    option = normalize_text(option)
    value = normalize_text(value)
    if not option or not value:
        return False
    if option == value:
        return True
    if len(value) >= 3 and (value in option or option in value):
        return True
    yes = {"yes", "y", "true"}
    no = {"no", "n", "false"}
    return (value in yes and option in yes) or (value in no and option in no)


def _compact_profile(profile):
    """Send only the facts needed to answer a question, never identity/contact data."""
    personal = profile.get("personal") or {}
    saved_answers = {
        str(key)[:300]: str(value)[:500]
        for key, value in list((profile.get("saved_answers") or {}).items())[:40]
        if value and not is_sensitive_text(key)
    }

    def short(value, limit=500):
        text = str(value or "").strip()
        return text[:limit]

    education = []
    for item in (profile.get("education") or [])[:6]:
        if isinstance(item, dict):
            education.append(
                {
                    "institution": short(item.get("institution"), 160),
                    "degree": short(item.get("degree"), 160),
                    "field_of_study": short(
                        item.get("field_of_study") or item.get("field"), 160
                    ),
                    "start_date": short(item.get("start_date"), 40),
                    "end_date": short(item.get("end_date"), 40),
                    "gpa": short(item.get("gpa"), 40),
                }
            )

    experience = []
    for item in (profile.get("experience") or [])[:8]:
        if isinstance(item, dict):
            experience.append(
                {
                    "company": short(
                        item.get("company")
                        or item.get("employer")
                        or item.get("organization"),
                        160,
                    ),
                    "title": short(item.get("title") or item.get("role"), 160),
                    "start_date": short(item.get("start_date"), 40),
                    "end_date": short(item.get("end_date"), 40),
                    "description": short(
                        item.get("description")
                        or item.get("responsibilities")
                        or item.get("achievements"),
                        700,
                    ),
                }
            )

    projects = []
    for item in (profile.get("projects") or [])[:6]:
        if isinstance(item, dict):
            projects.append(
                {
                    "name": short(item.get("name"), 160),
                    "description": short(item.get("description"), 500),
                    "technologies": short(
                        item.get("technologies") or item.get("tech"), 300
                    ),
                }
            )

    return {
        "personal": {
            "location": short(personal.get("location"), 160),
            "country": short(personal.get("country"), 120),
        },
        "education": education,
        "experience": experience,
        "skills": [
            short(skill, 120) for skill in (profile.get("skills") or [])[:30]
        ],
        "projects": projects,
        "saved_answers": saved_answers,
    }


def _prompt(profile_summary, field):
    return f"""You are a strict field-mapping component inside a job application agent.
Map one application field to facts explicitly present in the candidate profile.

You must NOT invent, infer, embellish, or use outside knowledge. If the profile
does not contain a direct answer, return answer_kind "none" with needs_review true.
If an answer would be composed or paraphrased from experience, return
answer_kind "generated" with needs_review true.
Do not answer sensitive or eligibility questions (salary, work authorization,
sponsorship, citizenship, demographics, disability, veteran status, criminal or
background checks, government IDs, security clearance, age/date of birth).

Candidate profile facts (no name, email, phone, or file contents):
{json.dumps(profile_summary, ensure_ascii=False)}

Field to map:
{json.dumps(field, ensure_ascii=False)}

Rules:
- matched_profile_key must name the supporting fact, for example
  "saved_answers.How did you hear about this job?", "skills", "personal.location",
  "education", "experience", or "projects". Use "" when unsupported.
- answer_kind "direct_fact" only when the value is explicitly present in the
  profile (or is one of the provided options and is supported by an explicit fact).
- answer_kind "generated" for any composed prose. Set needs_review true.
- answer_kind "none" when no fact supports an answer.
- suggested_value must be short (<= 500 characters) and must exactly match one
  of the options when options are provided.
- confidence is a number from 0.0 to 1.0.
- reason must cite the supporting fact or explain what is missing.
Return only the JSON object.
"""


RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "matched_profile_key": {"type": "STRING"},
        "answer_kind": {
            "type": "STRING",
            "enum": ["direct_fact", "generated", "none"],
        },
        "suggested_value": {"type": "STRING"},
        "confidence": {"type": "NUMBER"},
        "needs_review": {"type": "BOOLEAN"},
        "reason": {"type": "STRING"},
    },
    "required": [
        "matched_profile_key",
        "answer_kind",
        "suggested_value",
        "confidence",
        "needs_review",
        "reason",
    ],
}


class AIMapper:
    """Gemini field mapper with Python-side validation and a local cache."""

    def __init__(
        self,
        profile,
        api_key=None,
        model=None,
        threshold=None,
        timeout=None,
        max_fields=None,
        transport=None,
        auto_fill_generated=None,
    ):
        self.provider = os.getenv("AI_PROVIDER", "gemini").strip().lower() or "gemini"
        self.model = model or os.getenv("GEMINI_MODEL", DEFAULT_MODEL).strip()
        self.threshold = (
            _env_float("AI_CONFIDENCE_THRESHOLD", 0.75)
            if threshold is None
            else float(threshold)
        )
        self.timeout = (
            _env_int("AI_TIMEOUT_SECONDS", 25) if timeout is None else int(timeout)
        )
        self.max_retries = max(0, _env_int("AI_MAX_RETRIES", 2))
        self.max_fields = (
            _env_int("AI_MAX_FIELDS_PER_RUN", 8)
            if max_fields is None
            else int(max_fields)
        )
        self.auto_fill_generated = (
            _env_bool("AI_AUTO_FILL_GENERATED", False)
            if auto_fill_generated is None
            else bool(auto_fill_generated)
        )
        self.api_key = (api_key or os.getenv("GEMINI_API_KEY", "")).strip()
        self.transport = transport
        self.profile = profile
        self.profile_summary = _compact_profile(profile)
        self.calls_made = 0
        self.error_count = 0
        self.cache = {}

        enabled_setting = _env_bool("AI_ENABLED", True)
        self.enabled = (
            enabled_setting
            and self.provider == "gemini"
            and bool(self.api_key or self.transport)
        )

    @property
    def status(self):
        return {
            "enabled": self.enabled,
            "provider": self.provider,
            "model": self.model,
            "calls_made": self.calls_made,
            "errors": self.error_count,
            "max_fields": self.max_fields,
        }

    def _scrub(self, value):
        """Keep provider errors useful without ever writing the API key to logs."""
        text = str(value or "").replace("\n", " ")
        if self.api_key:
            text = text.replace(self.api_key, "[redacted]")
        return text[:500]

    def _request(self, payload):
        if self.transport is not None:
            return self.transport(payload)

        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self.api_key,
        }
        retryable_statuses = {429, 500, 502, 503, 504}

        for attempt in range(self.max_retries + 1):
            request = urllib.request.Request(
                GEMINI_ENDPOINT.format(model=self.model),
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            try:
                with urllib.request.urlopen(
                    request, timeout=self.timeout
                ) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                detail = ""
                try:
                    detail = exc.read().decode("utf-8", "replace")[:400]
                except Exception:
                    pass
                if exc.code in retryable_statuses and attempt < self.max_retries:
                    logger.warning(
                        "Gemini retryable HTTP status=%s attempt=%s",
                        exc.code,
                        attempt + 1,
                    )
                    time.sleep(min(2**attempt, 4))
                    continue
                raise AIMapperError(
                    f"Gemini HTTP {exc.code}" + (f": {detail}" if detail else "")
                ) from exc
            except urllib.error.URLError as exc:
                if attempt < self.max_retries:
                    logger.warning(
                        "Gemini connection retry attempt=%s reason=%s",
                        attempt + 1,
                        self._scrub(exc.reason),
                    )
                    time.sleep(min(2**attempt, 4))
                    continue
                raise AIMapperError(
                    f"Gemini connection failed: {exc.reason}"
                ) from exc
            except TimeoutError as exc:
                if attempt < self.max_retries:
                    logger.warning(
                        "Gemini timeout retry attempt=%s", attempt + 1
                    )
                    time.sleep(min(2**attempt, 4))
                    continue
                raise AIMapperError("Gemini request timed out.") from exc
            except json.JSONDecodeError as exc:
                raise AIMapperError("Gemini returned invalid JSON.") from exc

        raise AIMapperError("Gemini request failed after retries.")

    @staticmethod
    def _response_text(data):
        candidates = data.get("candidates") or []
        if not candidates:
            feedback = data.get("promptFeedback") or {}
            return "", str(feedback.get("blockReason") or "No candidates returned.")
        candidate = candidates[0]
        if candidate.get("finishReason") in ("SAFETY", "BLOCKED", "OTHER"):
            return "", f"Gemini stopped: {candidate.get('finishReason')}"
        parts = (candidate.get("content") or {}).get("parts") or []
        text = "".join(
            str(part.get("text") or "") for part in parts if isinstance(part, dict)
        ).strip()
        if not text:
            return "", f"Gemini returned no text ({candidate.get('finishReason') or 'unknown'})."
        return text, ""

    @staticmethod
    def _parse_json(text):
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(r"\s*```$", "", cleaned)
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end > start:
            cleaned = cleaned[start : end + 1]
        return json.loads(cleaned)

    def _fact_supported(self, key, value):
        key = (key or "").strip()
        value = (value or "").strip()
        if not key or not value:
            return False
        wanted = compact_text(value)
        if not wanted:
            return False

        if key.startswith("saved_answers"):
            saved = self.profile.get("saved_answers") or {}
            suffix = key[len("saved_answers") :].lstrip(".")
            if suffix:
                for question, answer in saved.items():
                    if normalize_text(question) == normalize_text(suffix) or compact_text(
                        question
                    ) == compact_text(suffix):
                        return compact_text(answer) == wanted
                return False
            return any(compact_text(answer) == wanted for answer in saved.values())

        if key.startswith("personal."):
            field_name = key.split(".", 1)[1]
            personal = self.profile.get("personal") or {}
            return compact_text(personal.get(field_name, "")) == wanted

        if key == "work_authorization":
            return compact_text(self.profile.get("work_authorization", "")) == wanted

        if key == "skills":
            skills = self.profile.get("skills") or []
            return any(compact_text(skill) == wanted for skill in skills)

        root = key.split(".", 1)[0].split("[", 1)[0]
        if root in PROFILE_COLLECTIONS:
            corpus = compact_text(
                json.dumps(self.profile.get(root) or [], ensure_ascii=False)
            )
            return bool(corpus) and wanted in corpus

        return False

    def _validate(self, parsed, field):
        if not isinstance(parsed, dict):
            raise AIMapperError("Gemini returned a non-object mapping.")

        try:
            confidence = float(parsed.get("confidence") or 0)
        except (TypeError, ValueError):
            confidence = 0.0
        if math.isnan(confidence) or math.isinf(confidence):
            confidence = 0.0
        confidence = min(1.0, max(0.0, confidence))

        kind = str(parsed.get("answer_kind") or "none").strip().lower()
        if kind not in ("direct_fact", "generated", "none"):
            kind = "none"
        value = str(parsed.get("suggested_value") or "").strip()
        reason = str(parsed.get("reason") or "").strip()[:500]
        matched_key = str(parsed.get("matched_profile_key") or "").strip()[:300]
        needs_review = bool(parsed.get("needs_review"))

        mapping = AIMapping(
            action="review",
            value=value,
            confidence=confidence,
            reason=reason,
            matched_profile_key=matched_key,
            answer_kind=kind,
            model=self.model,
            raw={"label": field.get("label") or field.get("question") or ""},
        )

        if kind == "none" or not value:
            mapping.reason = reason or "No grounded answer was found in the profile."
            return mapping

        if normalize_text(value) in PLACEHOLDER_VALUES:
            mapping.reason = "Gemini returned a placeholder instead of an answer."
            mapping.value = ""
            return mapping

        if is_sensitive_field(field):
            mapping.reason = (
                "This is a sensitive or eligibility question; it requires an explicit "
                "saved answer and is never answered by AI."
            )
            return mapping

        options = _option_texts(field.get("options"))
        if options and not any(_option_match(option, value) for option in options):
            mapping.reason = "Gemini's answer does not match any available option."
            return mapping

        if kind == "generated":
            if (
                self.auto_fill_generated
                and not needs_review
                and confidence >= self.threshold
            ):
                mapping.action = "fill"
                return mapping
            mapping.reason = (
                reason
                or "AI generated a suggested answer, but generated text requires review."
            )
            return mapping

        if needs_review or confidence < self.threshold:
            mapping.reason = reason or "AI confidence is below the auto-fill threshold."
            return mapping

        if not self._fact_supported(matched_key, value):
            mapping.reason = (
                "AI's answer is not traceable to an explicit profile fact, "
                "so it was not auto-filled."
            )
            return mapping

        mapping.action = "fill"
        return mapping

    def suggest(self, control, question=None, options=None):
        """Return an AIMapping. Provider errors are returned, never raised."""
        field = {
            "label": str(control.get("label") or control.get("name") or "")[:500],
            "question": str(
                question or control.get("question") or control.get("label") or ""
            )[:1000],
            "type": str(control.get("type") or control.get("tag") or "")[:40],
            "required": bool(control.get("required")),
            "options": _option_texts(
                options if options is not None else control.get("options")
            )[:60],
        }

        if not self.enabled:
            return AIMapping(
                action="skipped",
                reason="AI mapping is disabled or not configured.",
                model=self.model,
                raw={"label": field["label"]},
            )
        if field["type"] == "file":
            return AIMapping(
                action="skipped",
                reason="File fields are handled deterministically.",
                model=self.model,
                raw={"label": field["label"]},
            )
        if is_sensitive_field(field):
            return AIMapping(
                action="review",
                reason=(
                    "This is a sensitive or eligibility question; it requires an "
                    "explicit saved answer and is never answered by AI."
                ),
                model=self.model,
                raw={"label": field["label"]},
            )

        cache_key = json.dumps(field, sort_keys=True, ensure_ascii=False)
        if cache_key in self.cache:
            logger.debug("AI cache hit label=%r", field["label"][:160])
            return self.cache[cache_key]

        if self.calls_made >= self.max_fields:
            logger.warning(
                "AI field limit reached label=%r max_fields=%s",
                field["label"][:160],
                self.max_fields,
            )
            return AIMapping(
                action="skipped",
                reason="AI field limit reached for this run.",
                model=self.model,
                raw={"label": field["label"]},
            )

        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": _prompt(self.profile_summary, field)}
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.1,
                "responseMimeType": "application/json",
                "responseSchema": RESPONSE_SCHEMA,
            },
        }

        self.calls_made += 1
        logger.info(
            "AI request label=%r type=%s model=%s call=%s",
            field["label"][:160],
            field["type"],
            self.model,
            self.calls_made,
        )
        try:
            data = self._request(payload)
            text, problem = self._response_text(data)
            if problem:
                raise AIMapperError(problem)
            parsed = self._parse_json(text)
            mapping = self._validate(parsed, field)
        except Exception as exc:
            # AI is optional: any provider, parsing, or transport failure becomes
            # a review/error result and must never stop the application run.
            self.error_count += 1
            mapping = AIMapping(
                action="error",
                reason=self._scrub(exc) or "AI mapping failed.",
                model=self.model,
                raw={"label": field["label"]},
            )
            logger.warning(
                "AI error label=%r reason=%s",
                field["label"][:160],
                mapping.reason,
            )

        logger.info(
            "AI result label=%r action=%s kind=%s confidence=%.2f key=%s",
            field["label"][:160],
            mapping.action,
            mapping.answer_kind,
            mapping.confidence,
            mapping.matched_profile_key[:120],
        )
        self.cache[cache_key] = mapping
        return mapping


def build_ai_mapper(profile):
    """Return a configured mapper, or None when AI is disabled/unconfigured."""
    provider = os.getenv("AI_PROVIDER", "gemini").strip().lower() or "gemini"
    if provider != "gemini":
        return None
    if not _env_bool("AI_ENABLED", True):
        return None
    if not (os.getenv("GEMINI_API_KEY") or "").strip():
        return None
    mapper = AIMapper(profile)
    return mapper if mapper.enabled else None
