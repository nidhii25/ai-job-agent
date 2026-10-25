"""Safety and matching tests for Greenhouse fields.

These tests cover:
- degree/school/discipline option matching,
- explicit-only work authorization,
- safe derived facts from short labels,
- no inference from country, legal paragraphs, or demographic labels,
- React-select option waiting,
- optional fields not blocking submission.
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
from automation.greenhouse import (
    _education_value,
    _find_derived_answer,
    _work_authorization_answer,
    fill_application,
    find_best_degree_option,
    find_best_school_option,
    find_best_text_option,
    get_degree_level,
)

CANDIDATE_PROFILE = {
    "personal": {
        "full_name": "Nidhi Agrawal",
        "first_name": "Nidhi",
        "last_name": "Agrawal",
        "email": "devnidhi15@gmail.com",
        "phone": "6232230297",
        "location": "Indore, Madhya Pradesh",
        "country": "India",
        "linkedin_url": "https://linkedin.com/in/nidhiagrawal25",
        "github_url": "https://github.com/nidhii25",
        "website_url": "https://anidhi.vercel.app",
    },
    "education": [
        {
            "institution": "Shri Vaishnav Vidyapeeth Vishwavidyalaya, Indore",
            "degree": "B.Tech",
            "field_of_study": "Computer Science",
            "dates": "Aug 2023 - Jun 2027",
            "start_date": "2023",
            "end_date": "2027",
            "gpa": "9.46",
        }
    ],
    "experience": [
        {
            "company": "Tesreco",
            "title": "AI/ML Intern",
            "start_date": "Jun 2026",
            "end_date": "Jul 2026",
            "description": "Develop backend components using Python and FastAPI.",
        }
    ],
    "skills": ["Python", "FastAPI", "SQL", "Docker"],
    "projects": [
        {
            "name": "IntentIQ",
            "description": "AI Customer Support Platform",
            "technologies": "Python, FastAPI",
        }
    ],
    "resume_path": "",
    "cover_letter": "",
    "work_authorization": "",
    "saved_answers": {},
}

EXPLICIT_WORK_AUTH = (
    "Authorized to work in India. Requires visa sponsorship for employment "
    "outside India including the United States. Not authorized to work in the "
    "US without visa sponsorship."
)


def profile_with_explicit_work_auth():
    profile = json.loads(json.dumps(CANDIDATE_PROFILE))
    profile["work_authorization"] = EXPLICIT_WORK_AUTH
    return profile


def yes_no_control(label, question=None):
    return {
        "label": label,
        "question": question or label,
        "name": "",
        "id": "",
        "options": [{"value": "Yes", "text": "Yes"}, {"value": "No", "text": "No"}],
    }


class SmartDegreeMatchingTests(unittest.TestCase):
    def test_degree_level_normalization(self):
        self.assertEqual(get_degree_level("B.Tech"), "bachelor")
        self.assertEqual(get_degree_level("BTech in Computer Science"), "bachelor")
        self.assertEqual(get_degree_level("Bachelor of Technology"), "bachelor")
        self.assertEqual(get_degree_level("B.E. Computer Engineering"), "bachelor")
        self.assertEqual(get_degree_level("B.S. Software Engineering"), "bachelor")
        self.assertEqual(get_degree_level("Undergraduate"), "bachelor")
        self.assertEqual(get_degree_level("M.Tech"), "master")
        self.assertEqual(get_degree_level("Master of Science"), "master")
        self.assertEqual(get_degree_level("Ph.D. in Computer Science"), "doctorate")

    def test_btech_matches_bachelors_degree_option(self):
        options = [
            {"value": "hs", "text": "High School Diploma"},
            {"value": "assoc", "text": "Associate's Degree"},
            {"value": "bach", "text": "Bachelor's Degree"},
            {"value": "mast", "text": "Master's Degree"},
            {"value": "doc", "text": "Doctorate / Ph.D."},
        ]
        matched = find_best_degree_option("B.Tech", options)
        self.assertIsNotNone(matched)
        self.assertEqual(matched["value"], "bach")

    def test_btech_matches_undergraduate_option(self):
        options = [
            {"value": "grad", "text": "Graduate Degree"},
            {"value": "undergrad", "text": "Undergraduate Degree"},
            {"value": "phd", "text": "Ph.D."},
        ]
        matched = find_best_degree_option("B.Tech", options)
        self.assertIsNotNone(matched)
        self.assertEqual(matched["value"], "undergrad")

    def test_btech_matches_bachelor_of_science_if_no_btech(self):
        options = [
            {"value": "ba", "text": "Bachelor of Arts"},
            {"value": "bs", "text": "Bachelor of Science"},
            {"value": "ms", "text": "Master of Science"},
        ]
        matched = find_best_degree_option("B.Tech", options)
        self.assertIsNotNone(matched)
        self.assertEqual(matched["value"], "bs")

    def test_btech_falls_back_to_other_degree_when_no_bachelors(self):
        options = [
            {"value": "ms", "text": "Master of Science"},
            {"value": "phd", "text": "Doctor of Philosophy"},
            {"value": "other", "text": "Other"},
        ]
        matched = find_best_degree_option("B.Tech", options)
        self.assertIsNotNone(matched)
        self.assertEqual(matched["value"], "other")


class SmartSchoolMatchingTests(unittest.TestCase):
    def test_school_matches_other_when_college_not_in_options(self):
        options = [
            {"value": "1", "text": "Harvard University"},
            {"value": "2", "text": "Stanford University"},
            {"value": "3", "text": "Massachusetts Institute of Technology"},
            {"value": "other", "text": "Other / Not Listed"},
        ]
        matched = find_best_school_option(
            "Shri Vaishnav Vidyapeeth Vishwavidyalaya, Indore", options
        )
        self.assertIsNotNone(matched)
        self.assertEqual(matched["value"], "other")

    def test_school_matches_plain_other_option(self):
        options = [
            {"value": "col_1", "text": "UC Berkeley"},
            {"value": "col_2", "text": "Carnegie Mellon"},
            {"value": "other", "text": "Other"},
        ]
        matched = find_best_school_option(
            "Shri Vaishnav Vidyapeeth Vishwavidyalaya, Indore", options
        )
        self.assertIsNotNone(matched)
        self.assertEqual(matched["value"], "other")

    def test_school_matches_stripped_location_name(self):
        options = [
            {"value": "svvv", "text": "Shri Vaishnav Vidyapeeth Vishwavidyalaya"},
            {"value": "iit", "text": "IIT Bombay"},
            {"value": "other", "text": "Other"},
        ]
        matched = find_best_school_option(
            "Shri Vaishnav Vidyapeeth Vishwavidyalaya, Indore", options
        )
        self.assertIsNotNone(matched)
        self.assertEqual(matched["value"], "svvv")


class DisciplineMatchingTests(unittest.TestCase):
    def test_computer_science_matches_option(self):
        options = [
            {"value": "ee", "text": "Electrical Engineering"},
            {"value": "cs", "text": "Computer Science"},
            {"value": "other", "text": "Other"},
        ]
        matched = find_best_text_option("Computer Science", options)
        self.assertIsNotNone(matched)
        self.assertEqual(matched["value"], "cs")

    def test_discipline_control_detection(self):
        control = {"label": "Discipline", "id": "discipline--0", "question": ""}
        matched = find_best_text_option(
            "Computer Science", [{"value": "cs", "text": "Computer Science"}]
        )
        self.assertIsNotNone(matched)
        self.assertEqual(control["label"], "Discipline")


class ExplicitWorkAuthorizationTests(unittest.TestCase):
    def test_empty_profile_never_guesses_work_authorization(self):
        control = yes_no_control(
            "Are you legally authorized to work in the United States?"
        )
        self.assertEqual(_work_authorization_answer(CANDIDATE_PROFILE, control), "")

    def test_empty_profile_never_guesses_sponsorship(self):
        control = yes_no_control(
            "Will you now or in the future require visa sponsorship?"
        )
        self.assertEqual(_work_authorization_answer(CANDIDATE_PROFILE, control), "")

    def test_explicit_statement_answers_us_work_authorization(self):
        control = yes_no_control(
            "Are you legally authorized to work in the United States?"
        )
        self.assertEqual(
            _work_authorization_answer(profile_with_explicit_work_auth(), control),
            "No",
        )

    def test_explicit_statement_answers_us_sponsorship(self):
        control = yes_no_control(
            "Will you now or in the future require visa sponsorship?"
        )
        self.assertEqual(
            _work_authorization_answer(profile_with_explicit_work_auth(), control),
            "Yes",
        )

    def test_explicit_statement_answers_india_work_authorization(self):
        control = yes_no_control("Are you legally authorized to work in India?")
        self.assertEqual(
            _work_authorization_answer(profile_with_explicit_work_auth(), control),
            "Yes",
        )

    def test_explicit_statement_answers_india_sponsorship(self):
        control = yes_no_control("Will you require sponsorship to work in India?")
        self.assertEqual(
            _work_authorization_answer(profile_with_explicit_work_auth(), control),
            "No",
        )

    def test_citizenship_is_never_inferred_from_work_authorization(self):
        control = yes_no_control(
            "Are you a U.S. citizen or lawful permanent resident?"
        )
        self.assertEqual(
            _work_authorization_answer(profile_with_explicit_work_auth(), control),
            "",
        )

    def test_security_clearance_is_never_inferred(self):
        control = yes_no_control(
            "Security Clearance Type",
            "We are unable to sponsor candidates for a U.S. Security Clearance. "
            "Please provide the level of U.S. Security Clearance that you have today.",
        )
        self.assertEqual(
            _work_authorization_answer(profile_with_explicit_work_auth(), control),
            "",
        )

    def test_legal_acknowledgement_is_never_inferred(self):
        control = {
            "label": "Authorization and Acknowledgement",
            "question": (
                "By typing my name I certify this application is true. "
                "Claims under federal, state or local law are resolved by arbitration."
            ),
            "name": "question_123",
            "id": "question_123",
            "options": [],
        }
        self.assertEqual(
            _work_authorization_answer(profile_with_explicit_work_auth(), control),
            "",
        )


class DerivedFactsTests(unittest.TestCase):
    def test_graduation_year_derived_from_dates(self):
        control = {"label": "Graduation Year", "question": "What is your graduation year?"}
        self.assertEqual(_find_derived_answer(CANDIDATE_PROFILE, control), "2027")

    def test_graduation_month_derived_from_dates(self):
        control = {"label": "Graduation Month", "question": "What is your graduation month?"}
        self.assertEqual(_find_derived_answer(CANDIDATE_PROFILE, control), "June")

    def test_current_student_status_derived_from_end_date(self):
        control = {
            "label": "Are you a current student?",
            "question": "Are you currently enrolled in a degree program?",
        }
        self.assertEqual(_find_derived_answer(CANDIDATE_PROFILE, control), "Yes")

    def test_past_student_status_derived_from_end_date(self):
        profile = json.loads(json.dumps(CANDIDATE_PROFILE))
        profile["education"][0]["end_date"] = "2022"
        profile["education"][0]["dates"] = "Aug 2018 - May 2022"
        control = {
            "label": "Are you a current student?",
            "question": "Are you currently enrolled in a degree program?",
        }
        self.assertEqual(_find_derived_answer(profile, control), "No")

    def test_state_derived_from_short_label(self):
        control = {"label": "State / Province", "question": "State", "id": "state"}
        self.assertEqual(_find_derived_answer(CANDIDATE_PROFILE, control), "Madhya Pradesh")

    def test_city_derived_from_short_label(self):
        control = {"label": "City", "question": "City", "id": "city"}
        self.assertEqual(_find_derived_answer(CANDIDATE_PROFILE, control), "Indore")

    def test_highest_education_level_derived(self):
        control = {
            "label": "Highest level of education",
            "question": "Highest education achieved",
        }
        self.assertEqual(
            _find_derived_answer(CANDIDATE_PROFILE, control), "Bachelor's Degree"
        )

    def test_legal_paragraph_does_not_derive_state(self):
        control = {
            "label": "Authorization and Acknowledgement",
            "question": (
                "I understand that claims under federal, state or local law "
                "will be resolved by binding arbitration."
            ),
            "name": "question_8106143009",
            "id": "question_8106143009",
        }
        self.assertEqual(_find_derived_answer(CANDIDATE_PROFILE, control), "")

    def test_long_legal_label_does_not_derive_state(self):
        control = {
            "label": (
                "I certify that the information provided is true and understand "
                "that claims under federal, state or local law are resolved by arbitration."
            ),
            "question": "",
            "name": "question_legal",
            "id": "question_legal",
        }
        self.assertEqual(_find_derived_answer(CANDIDATE_PROFILE, control), "")

    def test_ethnicity_label_does_not_derive_city(self):
        control = {
            "label": "Are you Hispanic/Latino?",
            "question": "Are you Hispanic/Latino?",
            "name": "hispanic_ethnicity",
            "id": "hispanic_ethnicity",
        }
        self.assertEqual(_find_derived_answer(CANDIDATE_PROFILE, control), "")

    def test_unrelated_short_field_does_not_derive_city(self):
        control = {"label": "Ethnicity", "question": "Ethnicity", "id": "ethnicity"}
        self.assertEqual(_find_derived_answer(CANDIDATE_PROFILE, control), "")

    def test_notice_period_and_relocation_are_not_invented(self):
        for label in ("Notice period", "Willing to relocate"):
            self.assertEqual(
                _find_derived_answer(
                    CANDIDATE_PROFILE, {"label": label, "question": label}
                ),
                "",
            )


class AIMapperSafetyTests(unittest.TestCase):
    def setUp(self):
        self.profile = profile_with_explicit_work_auth()
        self.payloads = []

        def transport(payload):
            self.payloads.append(payload)
            return {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": json.dumps(
                                        {
                                            "matched_profile_key": "",
                                            "answer_kind": "none",
                                            "suggested_value": "",
                                            "confidence": 0.0,
                                            "needs_review": True,
                                            "reason": "No explicit fact.",
                                        }
                                    )
                                }
                            ]
                        }
                    }
                ]
            }

        self.transport = transport

    def mapper(self, **kwargs):
        return AIMapper(
            self.profile,
            api_key="dummy-key",
            transport=self.transport,
            **kwargs,
        )

    def test_compact_profile_has_no_hardcoded_derived_facts(self):
        mapper = self.mapper()
        self.assertNotIn("derived_facts", mapper.profile_summary)
        self.assertNotIn("authorized_in_india", json.dumps(mapper.profile_summary))
        self.assertNotIn("requires_us_sponsorship", json.dumps(mapper.profile_summary))

    def test_derived_fact_keys_are_not_supported(self):
        mapper = self.mapper()
        self.assertFalse(mapper._fact_supported("derived_facts.current_student", "Yes"))
        self.assertFalse(mapper._fact_supported("education", "Yes"))

    def test_work_authorization_requires_exact_explicit_value(self):
        mapper = self.mapper()
        self.assertFalse(mapper._fact_supported("work_authorization", "Yes"))
        self.assertTrue(
            mapper._fact_supported("work_authorization", EXPLICIT_WORK_AUTH)
        )

    def test_legal_attestation_is_not_sent_to_ai(self):
        mapper = self.mapper()

        def unexpected_request(_payload):
            self.fail("Legal attestations must not reach AI.")

        mapper.transport = unexpected_request
        mapping = mapper.suggest(
            {
                "label": "Authorization and Acknowledgement",
                "question": "By typing my name I certify this application is true.",
                "type": "text",
                "required": True,
            }
        )
        self.assertEqual(mapping.action, "review")
        self.assertEqual(mapper.calls_made, 0)
        self.assertIn("sensitive", mapping.reason)

    def test_quota_error_stops_further_calls(self):
        calls = []

        def quota_transport(payload):
            calls.append(payload)
            raise AIMapperError("Gemini HTTP 429: quota exceeded")

        mapper = AIMapper(
            self.profile,
            api_key="dummy-key",
            transport=quota_transport,
        )
        first = mapper.suggest(
            {
                "label": "What is your favorite color?",
                "question": "What is your favorite color?",
                "type": "text",
                "required": True,
            }
        )
        second = mapper.suggest(
            {
                "label": "What is your favorite food?",
                "question": "What is your favorite food?",
                "type": "text",
                "required": True,
            }
        )
        self.assertEqual(first.action, "error")
        self.assertEqual(second.action, "skipped")
        self.assertTrue(mapper.quota_exhausted)
        self.assertEqual(len(calls), 1)


class PlaywrightFormFillingIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self):
        self.context = self.browser.new_context()
        self.page = self.context.new_page()

    def tearDown(self):
        self.context.close()

    def test_form_fills_school_as_other_when_not_in_options(self):
        self.page.set_content(
            """
            <form id="application-form">
              <label for="school">School / College</label>
              <select id="school" name="school" required>
                <option value="">Select a school...</option>
                <option value="mit">MIT</option>
                <option value="stanford">Stanford</option>
                <option value="other">Other / Not Listed</option>
              </select>
            </form>
            """
        )
        result = fill_application(self.page, CANDIDATE_PROFILE)
        self.assertEqual(self.page.locator("#school").input_value(), "other")
        self.assertEqual(result.review_items, [])

    def test_form_fills_degree_as_bachelors_degree_when_options_have_levels(self):
        self.page.set_content(
            """
            <form id="application-form">
              <label for="degree">Degree</label>
              <select id="degree" name="degree" required>
                <option value="">Select degree...</option>
                <option value="hs">High School</option>
                <option value="bach">Bachelor's Degree</option>
                <option value="mast">Master's Degree</option>
              </select>
            </form>
            """
        )
        result = fill_application(self.page, CANDIDATE_PROFILE)
        self.assertEqual(self.page.locator("#degree").input_value(), "bach")
        self.assertEqual(result.review_items, [])

    def test_form_fills_discipline_from_profile(self):
        self.page.set_content(
            """
            <form id="application-form">
              <label for="discipline">Discipline</label>
              <select id="discipline" name="discipline" required>
                <option value="">Select discipline...</option>
                <option value="ee">Electrical Engineering</option>
                <option value="cs">Computer Science</option>
              </select>
            </form>
            """
        )
        result = fill_application(self.page, CANDIDATE_PROFILE)
        self.assertEqual(self.page.locator("#discipline").input_value(), "cs")
        self.assertEqual(result.review_items, [])

    def test_form_fills_explicit_us_work_authorization(self):
        self.page.set_content(
            """
            <form id="application-form">
              <fieldset>
                <legend>Are you legally authorized to work in the United States?</legend>
                <label><input type="radio" name="auth" value="Yes" required>Yes</label>
                <label><input type="radio" name="auth" value="No" required>No</label>
              </fieldset>
            </form>
            """
        )
        result = fill_application(self.page, profile_with_explicit_work_auth())
        self.assertTrue(self.page.locator('input[name="auth"][value="No"]').is_checked())
        self.assertEqual(result.review_items, [])

    def test_form_does_not_guess_work_authorization_from_country(self):
        self.page.set_content(
            """
            <form id="application-form">
              <fieldset>
                <legend>Are you legally authorized to work in the United States?</legend>
                <label><input type="radio" name="auth" value="Yes" required>Yes</label>
                <label><input type="radio" name="auth" value="No" required>No</label>
              </fieldset>
            </form>
            """
        )
        result = fill_application(self.page, CANDIDATE_PROFILE)
        self.assertFalse(self.page.locator('input[name="auth"][value="Yes"]').is_checked())
        self.assertFalse(self.page.locator('input[name="auth"][value="No"]').is_checked())
        self.assertEqual(len(result.review_items), 1)

    def test_legal_and_demographic_fields_are_not_derived(self):
        self.page.set_content(
            """
            <form id="application-form">
              <div class="field-wrapper">
                <input id="ack" name="ack" aria-label="Authorization and Acknowledgement" required>
                <p>I understand that claims under federal, state or local law are resolved by arbitration.</p>
              </div>
              <label for="ethnicity">Are you Hispanic/Latino?</label>
              <select id="ethnicity" name="ethnicity">
                <option value="">Select...</option>
                <option value="no">No</option>
                <option value="yes">Yes</option>
              </select>
            </form>
            """
        )
        result = fill_application(self.page, CANDIDATE_PROFILE)
        self.assertEqual(self.page.locator("#ack").input_value(), "")
        self.assertEqual(self.page.locator("#ethnicity").input_value(), "")
        self.assertEqual(
            [item["field_name"] for item in result.review_items],
            ["Authorization and Acknowledgement"],
        )

    def test_optional_unmatched_select_does_not_block_submission(self):
        self.page.set_content(
            """
            <form id="application-form">
              <label for="school">School</label>
              <select id="school" name="school">
                <option value="">Select a school...</option>
                <option value="mit">MIT</option>
              </select>
            </form>
            """
        )
        result = fill_application(self.page, CANDIDATE_PROFILE)
        self.assertEqual(self.page.locator("#school").input_value(), "")
        self.assertEqual(result.review_items, [])

    def test_delayed_combobox_options_are_waited_for(self):
        self.page.set_content(
            """
            <form id="application-form">
              <label for="school">School</label>
              <input id="school" role="combobox" aria-expanded="false" autocomplete="off">
              <div id="menu" role="listbox" hidden>
                <div role="option">MIT</div>
                <div role="option">Other / Not Listed</div>
              </div>
            </form>
            <script>
              const input = document.getElementById('school');
              const menu = document.getElementById('menu');
              let timer;
              input.addEventListener('input', () => {
                menu.hidden = true;
                clearTimeout(timer);
                timer = setTimeout(() => { menu.hidden = false; }, 700);
              });
              menu.querySelectorAll('[role="option"]').forEach((option) => {
                option.addEventListener('click', () => {
                  input.value = option.textContent.trim();
                  menu.hidden = true;
                });
              });
            </script>
            """
        )
        result = fill_application(self.page, CANDIDATE_PROFILE)
        self.assertEqual(self.page.locator("#school").input_value(), "Other / Not Listed")
        self.assertEqual(result.review_items, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
