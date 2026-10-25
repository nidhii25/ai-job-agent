"""Unit and local integration tests for the Gemini field mapper.

These tests never call the real Gemini API. They use injected transports and a
Playwright page built with set_content, so they are deterministic and offline.

Run from the repo root:
    backend\\venv\\Scripts\\python.exe -m unittest tests.test_ai_mapper -v
"""

import json
import os
import sys
import unittest

from playwright.sync_api import sync_playwright

BACKEND_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from automation.ai_mapper import AIMapper, AIMapperError, AIMapping
from automation.greenhouse import fill_application


PROFILE = {
    "personal": {
        "full_name": "Test Candidate",
        "first_name": "Test",
        "last_name": "Candidate",
        "email": "test.candidate@example.com",
        "phone": "555-0100",
        "location": "San Francisco, CA",
        "country": "United States",
        "linkedin_url": "https://www.linkedin.com/in/test-candidate",
        "github_url": "",
        "website_url": "",
    },
    "education": [
        {
            "institution": "Test University",
            "degree": "B.S. Computer Science",
            "field_of_study": "Computer Science",
            "dates": "Aug 2018 - May 2022",
            "start_date": "2018",
            "end_date": "2022",
            "gpa": "3.8",
        }
    ],
    "experience": [
        {
            "company": "Test Co",
            "title": "Software Engineer",
            "start_date": "2022",
            "end_date": "Present",
            "description": "Built Python and JavaScript services.",
        }
    ],
    "skills": ["Python", "JavaScript", "SQL"],
    "projects": [
        {
            "name": "Test Project",
            "description": "A small Python service.",
            "technologies": "Python, SQL",
        }
    ],
    "resume_path": "",
    "cover_letter": "",
    "work_authorization": "Authorized to work in the United States",
    "saved_answers": {
        "How did you hear about this job?": "LinkedIn",
        "Preferred work arrangement": "Remote",
    },
}


def gemini_response(mapping):
    return {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {"text": json.dumps(mapping, ensure_ascii=False)}
                    ]
                },
                "finishReason": "STOP",
            }
        ]
    }


BASE_MAPPING = {
    "matched_profile_key": "saved_answers.How did you hear about this job?",
    "answer_kind": "direct_fact",
    "suggested_value": "LinkedIn",
    "confidence": 0.95,
    "needs_review": False,
    "reason": "The saved answer says LinkedIn.",
}


class MapperValidationTests(unittest.TestCase):
    def setUp(self):
        self.old = {
            "AI_ENABLED": os.environ.get("AI_ENABLED"),
            "AI_PROVIDER": os.environ.get("AI_PROVIDER"),
            "AI_AUTO_FILL_GENERATED": os.environ.get("AI_AUTO_FILL_GENERATED"),
        }
        os.environ["AI_ENABLED"] = "true"
        os.environ["AI_PROVIDER"] = "gemini"
        os.environ.pop("AI_AUTO_FILL_GENERATED", None)
        self.payloads = []

    def tearDown(self):
        for key, value in self.old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def mapper(self, mapping=None, **kwargs):
        def transport(payload):
            self.payloads.append(payload)
            return gemini_response(mapping or BASE_MAPPING)

        return AIMapper(
            PROFILE,
            api_key="test-key",
            transport=transport,
            **kwargs,
        )

    def test_direct_saved_answer_can_fill(self):
        mapping = self.mapper().suggest(
            {
                "label": "How did you hear about this job?",
                "question": "How did you hear about this job?",
                "type": "text",
                "required": True,
            }
        )
        self.assertEqual(mapping.action, "fill")
        self.assertEqual(mapping.value, "LinkedIn")
        self.assertEqual(mapping.matched_profile_key, BASE_MAPPING["matched_profile_key"])

    def test_generated_prose_requires_review_by_default(self):
        mapping = self.mapper(
            {
                "matched_profile_key": "experience",
                "answer_kind": "generated",
                "suggested_value": "I have built Python and JavaScript services.",
                "confidence": 0.92,
                "needs_review": True,
                "reason": "Based on the Test Co experience.",
            }
        ).suggest(
            {
                "label": "Describe a project you are proud of.",
                "question": "Describe a project you are proud of.",
                "type": "textarea",
                "required": True,
            }
        )
        self.assertEqual(mapping.action, "review")
        self.assertEqual(mapping.value, "I have built Python and JavaScript services.")

    def test_generated_prose_can_be_enabled(self):
        mapper = self.mapper(
            {
                "matched_profile_key": "experience",
                "answer_kind": "generated",
                "suggested_value": "I have built Python and JavaScript services.",
                "confidence": 0.92,
                "needs_review": False,
                "reason": "Based on the Test Co experience.",
            },
            auto_fill_generated=True,
        )
        mapping = mapper.suggest(
            {
                "label": "Describe a project you are proud of.",
                "question": "Describe a project you are proud of.",
                "type": "textarea",
                "required": True,
            }
        )
        self.assertEqual(mapping.action, "fill")

    def test_low_confidence_requires_review(self):
        data = dict(BASE_MAPPING, confidence=0.4)
        mapping = self.mapper(data).suggest(
            {
                "label": "How did you hear about this job?",
                "question": "How did you hear about this job?",
                "type": "text",
                "required": True,
            }
        )
        self.assertEqual(mapping.action, "review")

    def test_hallucinated_fact_is_not_filled(self):
        data = dict(
            BASE_MAPPING,
            suggested_value="A referral from a friend",
            matched_profile_key="saved_answers.How did you hear about this job?",
        )
        mapping = self.mapper(data).suggest(
            {
                "label": "How did you hear about this job?",
                "question": "How did you hear about this job?",
                "type": "text",
                "required": True,
            }
        )
        self.assertEqual(mapping.action, "review")
        self.assertIn("not traceable", mapping.reason)

    def test_option_mismatch_requires_review(self):
        data = dict(
            matched_profile_key="saved_answers.Preferred work arrangement",
            answer_kind="direct_fact",
            suggested_value="Remote",
            confidence=0.95,
            needs_review=False,
            reason="Saved answer says Remote.",
        )
        mapping = self.mapper(data).suggest(
            {
                "label": "Are you willing to work on site?",
                "question": "Are you willing to work on site?",
                "type": "select",
                "required": True,
                "options": [
                    {"text": "Yes", "value": "yes"},
                    {"text": "No", "value": "no"},
                ],
            }
        )
        self.assertEqual(mapping.action, "review")
        self.assertIn("available option", mapping.reason)

    def test_sensitive_field_is_never_sent(self):
        mapper = self.mapper()
        mapping = mapper.suggest(
            {
                "label": "Are you legally authorized to work in the United States?",
                "question": "Are you legally authorized to work in the United States?",
                "type": "select",
                "required": True,
                "options": [{"text": "Yes", "value": "yes"}],
            }
        )
        self.assertEqual(mapping.action, "review")
        self.assertIn("sensitive", mapping.reason)
        self.assertEqual(len(self.payloads), 0)
        self.assertEqual(mapper.calls_made, 0)

    def test_profile_prompt_excludes_contact_details(self):
        mapper = self.mapper()
        mapper.suggest(
            {
                "label": "How did you hear about this job?",
                "question": "How did you hear about this job?",
                "type": "text",
                "required": True,
            }
        )
        self.assertEqual(len(self.payloads), 1)
        prompt = self.payloads[0]["contents"][0]["parts"][0]["text"]
        self.assertNotIn("test.candidate@example.com", prompt)
        self.assertNotIn("555-0100", prompt)
        self.assertNotIn("Test Candidate", prompt)
        self.assertIn('"saved_answers"', prompt)
        self.assertIn("Aug 2018 - May 2022", prompt)
        self.assertNotIn("Are you legally authorized", prompt)

    def test_request_includes_json_schema(self):
        mapper = self.mapper()
        mapper.suggest(
            {
                "label": "How did you hear about this job?",
                "question": "How did you hear about this job?",
                "type": "text",
                "required": True,
            }
        )
        config = self.payloads[0]["generationConfig"]
        self.assertEqual(config["responseMimeType"], "application/json")
        self.assertEqual(
            config["responseSchema"]["properties"]["confidence"]["type"], "NUMBER"
        )

    def test_provider_error_is_returned(self):
        def transport(payload):
            raise AIMapperError("provider unavailable")

        mapper = AIMapper(PROFILE, api_key="test-key", transport=transport)
        mapping = mapper.suggest(
            {
                "label": "How did you hear about this job?",
                "question": "How did you hear about this job?",
                "type": "text",
                "required": True,
            }
        )
        self.assertEqual(mapping.action, "error")
        self.assertEqual(mapper.error_count, 1)

    def test_transport_timeout_is_returned_not_raised(self):
        def transport(payload):
            raise TimeoutError("simulated timeout")

        mapper = AIMapper(PROFILE, api_key="test-key", transport=transport)
        mapping = mapper.suggest(
            {
                "label": "What is your preferred start date?",
                "question": "What is your preferred start date?",
                "type": "text",
                "required": True,
            }
        )
        self.assertEqual(mapping.action, "error")
        self.assertIn("simulated timeout", mapping.reason)
        self.assertEqual(mapper.error_count, 1)

    def test_api_key_is_scrubbed_from_errors(self):
        def transport(payload):
            raise ValueError("upstream rejected test-key")

        mapper = AIMapper(PROFILE, api_key="test-key", transport=transport)
        mapping = mapper.suggest(
            {
                "label": "What is your preferred start date?",
                "question": "What is your preferred start date?",
                "type": "text",
                "required": True,
            }
        )
        self.assertEqual(mapping.action, "error")
        self.assertNotIn("test-key", mapping.reason)
        self.assertIn("[redacted]", mapping.reason)

    def test_same_field_is_cached(self):
        mapper = self.mapper()
        field = {
            "label": "How did you hear about this job?",
            "question": "How did you hear about this job?",
            "type": "text",
            "required": True,
        }
        first = mapper.suggest(field)
        second = mapper.suggest(field)
        self.assertEqual(first.action, "fill")
        self.assertEqual(second.action, "fill")
        self.assertEqual(len(self.payloads), 1)

    def test_field_limit_is_enforced(self):
        mapper = self.mapper(max_fields=1)
        mapper.suggest(
            {
                "label": "How did you hear about this job?",
                "question": "How did you hear about this job?",
                "type": "text",
                "required": True,
            }
        )
        second = mapper.suggest(
            {
                "label": "What is your favorite color?",
                "question": "What is your favorite color?",
                "type": "text",
                "required": True,
            }
        )
        self.assertEqual(second.action, "skipped")


class StubMapper:
    def __init__(self, mapping):
        self.mapping = mapping
        self.calls = []

    def suggest(self, control, question=None, options=None):
        self.calls.append((control, question, options))
        return self.mapping


HTML = """
<!doctype html>
<html><body>
<form id="application-form">
  <div class="field"><label for="first_name">First Name</label>
    <input id="first_name" name="first_name" required></div>
  <div class="field"><label for="last_name">Last Name</label>
    <input id="last_name" name="last_name" required></div>
  <div class="field"><label for="email">Email</label>
    <input id="email" name="email" type="email" required></div>
  <div class="field"><label for="linkedin">LinkedIn Profile</label>
    <input id="linkedin" name="linkedin"></div>
  <div class="field"><label for="question_1000">Which programming language do you use most?
    <span class="required" aria-hidden="true">*</span></label>
    <input id="question_1000" name="question_1000" required></div>
</form>
</body></html>
"""


class FillerIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self):
        self.page = self.browser.new_page()
        self.page.set_content(HTML)

    def tearDown(self):
        self.page.close()

    def test_ai_fill_is_recorded_and_typed(self):
        stub = StubMapper(
            AIMapping(
                action="fill",
                value="Python",
                confidence=0.95,
                reason="Listed in skills.",
                matched_profile_key="skills",
                answer_kind="direct_fact",
            )
        )
        result = fill_application(self.page, PROFILE, ai_mapper=stub)
        self.assertEqual(self.page.input_value("#question_1000"), "Python")
        self.assertEqual(len(result.ai_filled), 1)
        self.assertEqual(result.ai_filled[0]["label"], "Which programming language do you use most?")
        self.assertEqual(result.review_items, [])
        self.assertEqual(len(stub.calls), 1)

    def test_ai_generated_answer_becomes_review_suggestion(self):
        stub = StubMapper(
            AIMapping(
                action="review",
                value="I have built Python services.",
                confidence=0.9,
                reason="Generated from experience; needs review.",
                matched_profile_key="experience",
                answer_kind="generated",
            )
        )
        result = fill_application(self.page, PROFILE, ai_mapper=stub)
        self.assertEqual(self.page.input_value("#question_1000"), "")
        self.assertEqual(len(result.review_items), 1)
        item = result.review_items[0]
        self.assertEqual(item["source"], "ai")
        self.assertEqual(item["suggested_value"], "I have built Python services.")
        self.assertEqual(result.ai_filled, [])

    def test_deterministic_saved_answer_skips_ai(self):
        profile = json.loads(json.dumps(PROFILE))
        profile["saved_answers"]["Which programming language do you use most?"] = "JavaScript"
        stub = StubMapper(
            AIMapping(action="fill", value="LinkedIn", confidence=0.99)
        )
        result = fill_application(self.page, profile, ai_mapper=stub)
        self.assertEqual(self.page.input_value("#question_1000"), "JavaScript")
        self.assertEqual(result.ai_filled, [])
        self.assertEqual(len(stub.calls), 0)

    def test_education_fields_fill_from_single_explicit_record(self):
        self.page.set_content(
            """
            <form id="application-form">
              <label for="school">School</label><input id="school" name="school">
              <label for="major">Field of study</label><input id="major" name="major">
              <label for="gpa">GPA</label><input id="gpa" name="gpa">
              <label for="graduation">Expected graduation date</label>
              <input id="graduation" name="graduation">
            </form>
            """
        )
        stub = StubMapper(AIMapping(action="error", reason="AI should not be used."))

        result = fill_application(self.page, PROFILE, ai_mapper=stub)

        self.assertEqual(self.page.input_value("#school"), "Test University")
        self.assertEqual(self.page.input_value("#major"), "Computer Science")
        self.assertEqual(self.page.input_value("#gpa"), "3.8")
        self.assertEqual(self.page.input_value("#graduation"), "2022")
        self.assertEqual(len(stub.calls), 0)
        self.assertEqual(result.review_items, [])

    def test_explicit_work_authorization_fills_radio_without_ai(self):
        self.page.set_content(
            """
            <form id="application-form">
              <fieldset>
                <legend>Are you legally authorized to work in the United States?</legend>
                <label><input type="radio" name="authorized" value="yes" required>Yes</label>
                <label><input type="radio" name="authorized" value="no" required>No</label>
              </fieldset>
            </form>
            """
        )
        stub = StubMapper(AIMapping(action="error", reason="AI should not be used."))

        result = fill_application(self.page, PROFILE, ai_mapper=stub)

        self.assertTrue(self.page.locator('input[value="yes"]').is_checked())
        self.assertEqual(len(stub.calls), 0)
        self.assertEqual(result.review_items, [])

    def test_explicit_work_license_answers_matching_question(self):
        self.page.set_content(
            """
            <form id="application-form">
              <fieldset>
                <legend>Do you have a license to work in the United States?</legend>
                <label><input type="radio" name="license" value="yes" required>Yes</label>
                <label><input type="radio" name="license" value="no" required>No</label>
              </fieldset>
            </form>
            """
        )
        profile = json.loads(json.dumps(PROFILE))
        profile["work_authorization"] = (
            "I have a license to work in the United States"
        )
        stub = StubMapper(AIMapping(action="error", reason="AI should not be used."))

        result = fill_application(self.page, profile, ai_mapper=stub)

        self.assertTrue(self.page.locator('input[value="yes"]').is_checked())
        self.assertEqual(len(stub.calls), 0)
        self.assertEqual(result.review_items, [])

    def test_work_authorization_is_not_guessed_from_country(self):
        self.page.set_content(
            """
            <form id="application-form">
              <fieldset>
                <legend>Are you legally authorized to work in the United States?</legend>
                <label><input type="radio" name="authorized" value="yes" required>Yes</label>
                <label><input type="radio" name="authorized" value="no" required>No</label>
              </fieldset>
            </form>
            """
        )
        profile = json.loads(json.dumps(PROFILE))
        profile["work_authorization"] = ""

        def unexpected_request(_payload):
            self.fail("Sensitive questions must not reach AI.")

        mapper = AIMapper(
            profile,
            api_key="test-key",
            transport=unexpected_request,
        )

        result = fill_application(self.page, profile, ai_mapper=mapper)

        self.assertFalse(self.page.locator('input[value="yes"]').is_checked())
        self.assertEqual(mapper.calls_made, 0)
        self.assertTrue(result.review_items)


if __name__ == "__main__":
    unittest.main(verbosity=2)
