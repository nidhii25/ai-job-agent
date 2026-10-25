"use client";

import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import {
  ApiError,
  emptyProfile,
  getProfile,
  prefillProfileFromResume,
  saveProfile,
  uploadCoverLetter,
} from "@/lib/api";
import type { Education, Experience, Profile } from "@/lib/api";
import FilePicker from "@/components/FilePicker";

const inputClass =
  "w-full rounded border border-gray-300 px-3 py-2 text-sm text-gray-800 focus:border-transparent focus:outline-none focus:ring-2 focus:ring-blue-500";

function errorMessage(error: unknown): string {
  return error instanceof ApiError || error instanceof Error
    ? error.message
    : String(error);
}

function fileName(path: string): string {
  if (!path) return "";
  const parts = path.split(/[\\/]/);
  return parts[parts.length - 1];
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <span className="mb-1 block text-xs font-medium text-gray-600">
        {label}
      </span>
      {children}
    </div>
  );
}

function ListEditor({
  label,
  value,
  onChange,
  rows = 3,
  placeholder,
}: {
  label: string;
  value: string[];
  onChange: (next: string[]) => void;
  rows?: number;
  placeholder?: string;
}) {
  const [text, setText] = useState(value.join("\n"));
  const lastEmitted = useRef(value.join("\n"));

  // Reset the editor when the value changes from outside (e.g. an item above
  // was removed), but not while the user is typing in this editor.
  useEffect(() => {
    const next = value.join("\n");
    if (next !== lastEmitted.current) {
      setText(next);
      lastEmitted.current = next;
    }
  }, [value]);

  return (
    <Field label={`${label} (one per line)`}>
      <textarea
        value={text}
        rows={rows}
        placeholder={placeholder}
        onChange={(event) => {
          const raw = event.target.value;
          const parsed = raw
            .split("\n")
            .map((line) => line.trim())
            .filter(Boolean);
          setText(raw);
          lastEmitted.current = parsed.join("\n");
          onChange(parsed);
        }}
        className={`${inputClass} resize-y`}
      />
    </Field>
  );
}

function readFileAsBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = String(reader.result ?? "");
      const comma = result.indexOf(",");
      resolve(comma >= 0 ? result.slice(comma + 1) : result);
    };
    reader.onerror = () => reject(new Error("Could not read the selected file"));
    reader.readAsDataURL(file);
  });
}

export default function ProfilePage() {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadingCoverLetter, setUploadingCoverLetter] = useState(false);
  const [newAnswerKey, setNewAnswerKey] = useState("");
  const [newAnswerValue, setNewAnswerValue] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [resumeWarnings, setResumeWarnings] = useState<string[]>([]);
  const [coverLetterWarnings, setCoverLetterWarnings] = useState<string[]>([]);

  useEffect(() => {
    getProfile()
      .then((data) =>
        setProfile({
          ...emptyProfile,
          ...data,
          personal: { ...emptyProfile.personal, ...data.personal },
        })
      )
      .catch((err) => setError(errorMessage(err)))
      .finally(() => setLoading(false));
  }, []);

  const updatePersonal = (field: keyof Profile["personal"], value: string) => {
    setProfile((current) =>
      current
        ? { ...current, personal: { ...current.personal, [field]: value } }
        : current
    );
  };

  const updateEducation = (index: number, patch: Partial<Education>) => {
    setProfile((current) =>
      current
        ? {
            ...current,
            education: current.education.map((item, i) =>
              i === index ? { ...item, ...patch } : item
            ),
          }
        : current
    );
  };

  const updateExperience = (index: number, patch: Partial<Experience>) => {
    setProfile((current) =>
      current
        ? {
            ...current,
            experience: current.experience.map((item, i) =>
              i === index ? { ...item, ...patch } : item
            ),
          }
        : current
    );
  };

  const handleSave = async () => {
    if (!profile) return;
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      await saveProfile(profile);
      setMessage("Profile saved successfully.");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  const handleResumeUpload = async (file: File) => {
    setError(null);
    setMessage(null);
    setResumeWarnings([]);

    if (file.size > 10 * 1024 * 1024) {
      setError("Resume must be 10 MB or smaller.");
      return;
    }

    setUploading(true);
    try {
      const content = await readFileAsBase64(file);
      const result = await prefillProfileFromResume(file.name, content);
      setProfile((current) => {
        if (!current) return current;

        const personal = { ...current.personal };
        (
          Object.keys(result.profile.personal) as (keyof Profile["personal"])[]
        ).forEach((key) => {
          const value = result.profile.personal[key];
          if (value) personal[key] = value;
        });

        return {
          ...current,
          resume_path: result.resume_path,
          personal,
          education: result.profile.education.length
            ? result.profile.education.map((item) => ({
                ...item,
                gpa: item.gpa || null,
              }))
            : current.education,
          experience: result.profile.experience.length
            ? result.profile.experience.map((item) => ({
                ...item,
                responsibilities: item.responsibilities || [],
                achievements: item.achievements || [],
              }))
            : current.experience,
          skills: result.profile.skills.length
            ? result.profile.skills
            : current.skills,
          projects: result.profile.projects.length
            ? result.profile.projects
            : current.projects,
        };
      });
      setResumeWarnings(result.warnings);
      setMessage(
        result.fields_found > 0
          ? `Resume parsed: ${result.fields_found} value(s) filled in. Review the fields below, then click Save Profile.`
          : "Resume uploaded. No profile fields could be extracted; fill them in manually and click Save Profile."
      );
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setUploading(false);
    }
  };

  const handleCoverLetterUpload = async (file: File) => {
    setError(null);
    setMessage(null);
    setCoverLetterWarnings([]);

    if (file.size > 10 * 1024 * 1024) {
      setError("Cover letter must be 10 MB or smaller.");
      return;
    }

    setUploadingCoverLetter(true);
    try {
      const content = await readFileAsBase64(file);
      const result = await uploadCoverLetter(file.name, content);
      setProfile((current) =>
        current
          ? {
              ...current,
              cover_letter: result.cover_letter,
              cover_letter_path: result.cover_letter_path,
            }
          : current
      );
      setCoverLetterWarnings(result.warnings);
      setMessage("Cover letter uploaded and saved to the profile.");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setUploadingCoverLetter(false);
    }
  };

  const addSavedAnswer = () => {
    const key = newAnswerKey.trim();
    if (!key || !profile) return;

    setProfile({
      ...profile,
      saved_answers: { ...profile.saved_answers, [key]: newAnswerValue.trim() },
    });
    setNewAnswerKey("");
    setNewAnswerValue("");
  };

  const removeSavedAnswer = (key: string) => {
    if (!profile) return;
    const next = { ...profile.saved_answers };
    delete next[key];
    setProfile({ ...profile, saved_answers: next });
  };

  if (loading) {
    return (
      <div className="min-h-screen p-6">
        <p className="mx-auto max-w-3xl text-sm text-gray-500">
          Loading profile...
        </p>
      </div>
    );
  }

  if (!profile) {
    return (
      <div className="min-h-screen p-6">
        <div className="mx-auto max-w-3xl rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          {error || "Could not load the profile."}
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background p-6">
      <div className="mx-auto max-w-3xl">
        <h1 className="mb-6 text-2xl font-bold">My Profile</h1>

        {error && (
          <div className="mb-4 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">
            {error}
          </div>
        )}
        {message && (
          <div className="mb-4 rounded border border-green-200 bg-green-50 p-3 text-sm text-green-700">
            {message}
          </div>
        )}

        <section className="mb-6 rounded-lg border border-blue-200 bg-blue-50 p-5 shadow-sm">
          <h2 className="mb-1 text-lg font-medium">Autofill from Resume</h2>
          <p className="mb-3 text-sm text-gray-700">
            Upload your resume first. The app extracts facts that are explicitly
            in the resume and fills the profile fields below for you to review.
            The extracted profile fields are not saved until you click Save
            Profile; the resume file itself is stored immediately.
          </p>
          <FilePicker
            accept=".pdf,.doc,.docx,.txt,.rtf"
            buttonLabel={profile.resume_path ? "Replace Resume" : "Choose Resume"}
            selectedName={fileName(profile.resume_path)}
            onSelect={handleResumeUpload}
            disabled={uploading}
            helpText="Supports PDF, DOCX, TXT, and RTF. Legacy .doc files can be stored but not parsed automatically. Max 10 MB. Resume text is sent to Gemini for extraction when AI is enabled."
          />
          {uploading && (
            <p className="mt-2 text-sm font-medium text-blue-700">
              Reading resume and extracting profile details...
            </p>
          )}
          {resumeWarnings.length > 0 && (
            <div className="mt-3 rounded border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
              <p className="mb-1 font-medium">Review notes</p>
              <ul className="list-inside list-disc space-y-1">
                {resumeWarnings.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            </div>
          )}
        </section>

        <section className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
          <h2 className="mb-4 text-lg font-medium">Personal Details</h2>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Field label="Full Name">
              <input
                value={profile.personal.full_name}
                onChange={(event) =>
                  updatePersonal("full_name", event.target.value)
                }
                placeholder="Full name"
                className={inputClass}
              />
            </Field>
            <Field label="First Name (optional override)">
              <input
                value={profile.personal.first_name}
                onChange={(event) =>
                  updatePersonal("first_name", event.target.value)
                }
                placeholder="Defaults to the first word of Full Name"
                className={inputClass}
              />
            </Field>
            <Field label="Last Name (optional override)">
              <input
                value={profile.personal.last_name}
                onChange={(event) =>
                  updatePersonal("last_name", event.target.value)
                }
                placeholder="Defaults to the rest of Full Name"
                className={inputClass}
              />
            </Field>
            <Field label="Email">
              <input
                type="email"
                value={profile.personal.email}
                onChange={(event) =>
                  updatePersonal("email", event.target.value)
                }
                placeholder="email@example.com"
                className={inputClass}
              />
            </Field>
            <Field label="Phone">
              <input
                value={profile.personal.phone}
                onChange={(event) =>
                  updatePersonal("phone", event.target.value)
                }
                placeholder="Phone number"
                className={inputClass}
              />
            </Field>
            <Field label="Location">
              <input
                value={profile.personal.location}
                onChange={(event) =>
                  updatePersonal("location", event.target.value)
                }
                placeholder="City, Country"
                className={inputClass}
              />
            </Field>
            <Field label="Country">
              <input
                value={profile.personal.country}
                onChange={(event) =>
                  updatePersonal("country", event.target.value)
                }
                placeholder="e.g., United States"
                className={inputClass}
              />
            </Field>
            <Field label="LinkedIn URL">
              <input
                value={profile.personal.linkedin_url}
                onChange={(event) =>
                  updatePersonal("linkedin_url", event.target.value)
                }
                placeholder="https://linkedin.com/in/username"
                className={inputClass}
              />
            </Field>
            <Field label="GitHub URL">
              <input
                value={profile.personal.github_url}
                onChange={(event) =>
                  updatePersonal("github_url", event.target.value)
                }
                placeholder="https://github.com/username"
                className={inputClass}
              />
            </Field>
            <Field label="Portfolio / Website">
              <input
                value={profile.personal.website_url}
                onChange={(event) =>
                  updatePersonal("website_url", event.target.value)
                }
                placeholder="https://your-site.com"
                className={inputClass}
              />
            </Field>
          </div>
          <div className="mt-4">
            <Field label="Work Authorization">
              <input
                value={profile.work_authorization}
                onChange={(event) =>
                  setProfile({
                    ...profile,
                    work_authorization: event.target.value,
                  })
                }
                placeholder="e.g., Authorized to work in the US without sponsorship"
                className={inputClass}
              />
            </Field>
            <p className="mt-1 text-xs text-gray-500">
              Enter this explicitly. The agent will never infer or fabricate
              eligibility answers.
            </p>
          </div>
        </section>

        <section className="mt-6 rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
          <h2 className="mb-4 text-lg font-medium">Education</h2>

          {profile.education.map((education, index) => (
            <div
              key={index}
              className="mb-4 rounded border border-gray-200 p-4"
            >
              <h3 className="mb-3 text-sm font-semibold">
                Education {index + 1}
              </h3>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <Field label="Institution">
                  <input
                    value={education.institution}
                    onChange={(event) =>
                      updateEducation(index, {
                        institution: event.target.value,
                      })
                    }
                    placeholder="Institution name"
                    className={inputClass}
                  />
                </Field>
                <Field label="Degree">
                  <input
                    value={education.degree}
                    onChange={(event) =>
                      updateEducation(index, { degree: event.target.value })
                    }
                    placeholder="e.g., BS Computer Science"
                    className={inputClass}
                  />
                </Field>
                <Field label="Field of Study">
                  <input
                    value={education.field_of_study}
                    onChange={(event) =>
                      updateEducation(index, {
                        field_of_study: event.target.value,
                      })
                    }
                    placeholder="Field of study"
                    className={inputClass}
                  />
                </Field>
                <Field label="GPA">
                  <input
                    value={education.gpa ?? ""}
                    onChange={(event) =>
                      updateEducation(index, { gpa: event.target.value })
                    }
                    placeholder="e.g., 3.5"
                    className={inputClass}
                  />
                </Field>
                <Field label="Dates">
                  <input
                    value={education.dates}
                    onChange={(event) =>
                      updateEducation(index, { dates: event.target.value })
                    }
                    placeholder="e.g., 2020 - 2024"
                    className={inputClass}
                  />
                </Field>
              </div>
              <button
                onClick={() =>
                  setProfile({
                    ...profile,
                    education: profile.education.filter((_, i) => i !== index),
                  })
                }
                className="mt-3 text-sm text-red-600 hover:text-red-800"
              >
                Remove
              </button>
            </div>
          ))}

          <button
            onClick={() =>
              setProfile({
                ...profile,
                education: [
                  ...profile.education,
                  {
                    institution: "",
                    degree: "",
                    field_of_study: "",
                    dates: "",
                    gpa: null,
                  },
                ],
              })
            }
            className="rounded bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700"
          >
            Add Education
          </button>
        </section>

        <section className="mt-6 rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
          <h2 className="mb-4 text-lg font-medium">Experience</h2>

          {profile.experience.map((experience, index) => (
            <div
              key={index}
              className="mb-4 rounded border border-gray-200 p-4"
            >
              <h3 className="mb-3 text-sm font-semibold">
                Experience {index + 1}
              </h3>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <Field label="Employer">
                  <input
                    value={experience.employer}
                    onChange={(event) =>
                      updateExperience(index, {
                        employer: event.target.value,
                      })
                    }
                    placeholder="Employer name"
                    className={inputClass}
                  />
                </Field>
                <Field label="Title">
                  <input
                    value={experience.title}
                    onChange={(event) =>
                      updateExperience(index, { title: event.target.value })
                    }
                    placeholder="Job title"
                    className={inputClass}
                  />
                </Field>
                <Field label="Dates">
                  <input
                    value={experience.dates}
                    onChange={(event) =>
                      updateExperience(index, { dates: event.target.value })
                    }
                    placeholder="e.g., Jan 2023 - Present"
                    className={inputClass}
                  />
                </Field>
              </div>
              <div className="mt-3 grid grid-cols-1 gap-3">
                <ListEditor
                  label="Responsibilities"
                  value={experience.responsibilities}
                  onChange={(next) =>
                    updateExperience(index, { responsibilities: next })
                  }
                  placeholder="Built the reporting pipeline"
                />
                <ListEditor
                  label="Achievements"
                  value={experience.achievements}
                  onChange={(next) =>
                    updateExperience(index, { achievements: next })
                  }
                  placeholder="Reduced report time by 40%"
                />
              </div>
              <button
                onClick={() =>
                  setProfile({
                    ...profile,
                    experience: profile.experience.filter(
                      (_, i) => i !== index
                    ),
                  })
                }
                className="mt-3 text-sm text-red-600 hover:text-red-800"
              >
                Remove
              </button>
            </div>
          ))}

          <button
            onClick={() =>
              setProfile({
                ...profile,
                experience: [
                  ...profile.experience,
                  {
                    employer: "",
                    title: "",
                    dates: "",
                    responsibilities: [],
                    achievements: [],
                  },
                ],
              })
            }
            className="rounded bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700"
          >
            Add Experience
          </button>
        </section>

        <section className="mt-6 rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
          <h2 className="mb-4 text-lg font-medium">Skills & Projects</h2>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <ListEditor
              label="Skills"
              value={profile.skills}
              onChange={(next) => setProfile({ ...profile, skills: next })}
              placeholder="Python"
            />
            <ListEditor
              label="Projects"
              value={profile.projects}
              onChange={(next) => setProfile({ ...profile, projects: next })}
              placeholder="Portfolio analyzer"
            />
          </div>
        </section>

        <section className="mt-6 rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
          <h2 className="mb-4 text-lg font-medium">Resume & Cover Letter</h2>

          <Field label="Resume File Path">
            <input
              value={profile.resume_path}
              onChange={(event) =>
                setProfile({ ...profile, resume_path: event.target.value })
              }
              placeholder="C:/Users/you/Documents/resume.pdf"
              className={inputClass}
            />
          </Field>
          <p className="mt-2 text-xs text-gray-500">
            To replace the file and prefill fields, use Autofill from Resume at
            the top of this page. Uploaded files are stored in
            backend/uploads.
          </p>

          <div className="mt-4">
            <Field label="Cover Letter File">
              <FilePicker
                accept=".pdf,.doc,.docx,.txt,.rtf"
                buttonLabel={
                  profile.cover_letter_path
                    ? "Replace Cover Letter"
                    : "Choose Cover Letter"
                }
                selectedName={fileName(profile.cover_letter_path)}
                onSelect={handleCoverLetterUpload}
                disabled={uploadingCoverLetter}
                helpText="Upload a PDF, DOCX, TXT, or RTF file to store it and fill the cover letter text below. Max 10 MB."
              />
            </Field>
            {coverLetterWarnings.length > 0 && (
              <div className="mt-3 rounded border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
                <p className="mb-1 font-medium">Review notes</p>
                <ul className="list-inside list-disc space-y-1">
                  {coverLetterWarnings.map((warning) => (
                    <li key={warning}>{warning}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          <div className="mt-4">
            <Field label="Cover Letter">
              <textarea
                value={profile.cover_letter}
                onChange={(event) =>
                  setProfile({ ...profile, cover_letter: event.target.value })
                }
                rows={5}
                placeholder="Optional reusable cover letter"
                className={`${inputClass} resize-y`}
              />
            </Field>
          </div>
        </section>

        <section className="mt-6 rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
          <h2 className="mb-1 text-lg font-medium">Saved Answers</h2>
          <p className="mb-4 text-xs text-gray-500">
            Approved answers the agent may reuse. Only answers saved here are
            treated as approved.
          </p>

          {Object.entries(profile.saved_answers).length === 0 ? (
            <p className="text-sm text-gray-500">No saved answers yet.</p>
          ) : (
            <div className="space-y-3">
              {Object.entries(profile.saved_answers).map(([key, value]) => (
                <div
                  key={key}
                  className="rounded border border-gray-200 p-3"
                >
                  <div className="flex items-start justify-between gap-3">
                    <span className="text-sm font-medium text-gray-800">
                      {key}
                    </span>
                    <button
                      onClick={() => removeSavedAnswer(key)}
                      className="text-sm text-red-600 hover:text-red-800"
                    >
                      Remove
                    </button>
                  </div>
                  <input
                    value={value}
                    onChange={(event) =>
                      setProfile({
                        ...profile,
                        saved_answers: {
                          ...profile.saved_answers,
                          [key]: event.target.value,
                        },
                      })
                    }
                    className={`${inputClass} mt-2`}
                  />
                </div>
              ))}
            </div>
          )}

          <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Field label="Question">
              <input
                value={newAnswerKey}
                onChange={(event) => setNewAnswerKey(event.target.value)}
                placeholder="e.g., Are you willing to relocate?"
                className={inputClass}
              />
            </Field>
            <Field label="Approved Answer">
              <input
                value={newAnswerValue}
                onChange={(event) => setNewAnswerValue(event.target.value)}
                placeholder="e.g., Yes"
                className={inputClass}
              />
            </Field>
          </div>
          <button
            onClick={addSavedAnswer}
            disabled={!newAnswerKey.trim()}
            className="mt-3 rounded bg-gray-200 px-4 py-2 text-sm font-semibold text-gray-700 hover:bg-gray-300 disabled:text-gray-400"
          >
            Add Saved Answer
          </button>
        </section>

        <div className="mt-8 flex items-center gap-4">
          <button
            onClick={handleSave}
            disabled={saving}
            className="rounded bg-blue-600 px-5 py-2 font-semibold text-white hover:bg-blue-700 disabled:bg-blue-300"
          >
            {saving ? "Saving..." : "Save Profile"}
          </button>
          <p className="text-xs text-gray-500">
            Saves to the backend profile.json.
          </p>
        </div>
      </div>
    </div>
  );
}
