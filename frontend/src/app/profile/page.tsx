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

function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <div>
      <div className="flex items-center justify-between mb-1.5">
        <label className="block text-xs font-semibold uppercase tracking-wider text-[#5b616e]">
          {label}
        </label>
        {hint && <span className="text-[11px] text-[#7c828a]">{hint}</span>}
      </div>
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
        className="text-input resize-y !h-auto min-h-[90px]"
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

const SECTIONS = [
  { id: "all", label: "Overview" },
  { id: "personal", label: "Personal Details" },
  { id: "experience", label: "Work Experience" },
  { id: "education", label: "Education" },
  { id: "skills", label: "Skills & Projects" },
  { id: "documents", label: "Documents" },
  { id: "saved-answers", label: "Saved Answers" },
];

export default function ProfilePage() {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [activeTab, setActiveTab] = useState("all");
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
      setMessage("Profile changes saved to local profile.json.");
      setTimeout(() => setMessage(null), 4000);
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
          ? `Resume parsed: ${result.fields_found} value(s) extracted and filled below. Review fields, then click Save Profile.`
          : "Resume attached. No automated fields could be parsed; fill them manually and click Save Profile."
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
      setMessage("Cover letter attached and synchronized with profile.");
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
      <div className="content-container py-24 text-center">
        <span className="inline-block h-6 w-6 rounded-full border-2 border-[#0052ff]/30 border-t-[#0052ff] animate-spin mb-4" />
        <p className="text-sm text-[#7c828a]">Loading candidate profile...</p>
      </div>
    );
  }

  if (!profile) {
    return (
      <div className="content-container py-24">
        <div className="rounded-2xl border border-[#dee1e6] bg-[#fafbfc] p-6 text-sm text-[#cf202f]">
          {error || "Could not load the profile from backend/profile.json."}
        </div>
      </div>
    );
  }

  const initial = (profile.personal.full_name || profile.personal.first_name || "A")
    .trim()
    .charAt(0)
    .toUpperCase();

  const isVisible = (id: string) => activeTab === "all" || activeTab === id;

  return (
    <div className="w-full flex-1 flex flex-col pb-24">
      {/* Dark Editorial Hero Band */}
      <section className="hero-band-dark">
        <div className="content-container">
          <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-8">
            <div className="max-w-xl">
              <span className="badge-pill-dark mb-4">
                Grounding Source
              </span>
              <h1 className="display-xl text-white">
                Candidate Profile.
              </h1>
              <p className="mt-4 text-base text-[#a8acb3] leading-relaxed">
                Your single source of truth for all automated job applications.
                Every answer filled into Greenhouse is strictly grounded in these verified records.
              </p>
            </div>

            {/* Profile Avatar Badge */}
            <div className="flex items-center gap-4 p-4 rounded-3xl border border-[#292c32] bg-[#16181c]">
              <div className="grid h-16 w-16 place-items-center rounded-full bg-[#0052ff] text-2xl font-bold text-white shadow-md">
                {initial}
              </div>
              <div>
                <span className="font-semibold text-white block text-base">
                  {profile.personal.full_name || "Unnamed Candidate"}
                </span>
                <span className="text-xs text-[#a8acb3] block mt-0.5">
                  {profile.personal.email || "No email specified"}
                </span>
                <span className="inline-flex items-center gap-1 text-[11px] text-[#05b169] mt-1 font-mono">
                  ● Verified Local Storage
                </span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Main Profile Form */}
      <section className="py-10 bg-white flex-1">
        <div className="content-container">
          <div className="mx-auto max-w-4xl space-y-10">
            {/* Quick Section Tabs */}
            <div className="flex flex-wrap items-center gap-1.5 pb-4 border-b border-[#dee1e6]">
              {SECTIONS.map((sec) => {
                const active = activeTab === sec.id;
                return (
                  <button
                    key={sec.id}
                    onClick={() => setActiveTab(sec.id)}
                    className={`rounded-full px-4 py-2 text-xs font-semibold tracking-wide transition-all ${
                      active
                        ? "bg-[#0a0b0d] text-white"
                        : "bg-[#eef0f3] text-[#5b616e] hover:bg-[#e2e5ea] hover:text-[#0a0b0d]"
                    }`}
                  >
                    {sec.label}
                  </button>
                );
              })}
            </div>

            {/* Feedback Notifications */}
            {error && (
              <div className="rounded-2xl border border-[#dee1e6] bg-[#fafbfc] p-4 text-sm text-[#cf202f]">
                {error}
              </div>
            )}
            {message && (
              <div className="rounded-2xl border border-[#dee1e6] bg-[#fafbfc] p-4 text-sm text-[#05b169]">
                {message}
              </div>
            )}

            {/* Autofill from Resume Highlight Card */}
            {(activeTab === "all" || activeTab === "documents") && (
              <div className="feature-card !p-8 border-2 border-[#0052ff]/20 bg-[#fafbfc]">
                <div className="flex items-start gap-4 mb-4">
                  <div className="asset-icon-circular text-[#0052ff] bg-white border border-[#dee1e6]">
                    ⚡
                  </div>
                  <div>
                    <h2 className="title-md text-[#0a0b0d]">Autofill from Resume</h2>
                    <p className="body-sm text-[#5b616e] mt-1">
                      Attach your resume first. The agent parses explicitly stated details to prefill the fields below.
                      Extracted fields are staged for your review and only written to disk when you click Save Profile.
                    </p>
                  </div>
                </div>

                <div className="mt-5">
                  <FilePicker
                    accept=".pdf,.doc,.docx,.txt,.rtf"
                    buttonLabel={profile.resume_path ? "Replace Resume" : "Attach Resume File"}
                    selectedName={fileName(profile.resume_path)}
                    onSelect={handleResumeUpload}
                    disabled={uploading}
                    helpText="PDF, DOCX, TXT, or RTF up to 10 MB. Parsed locally using Gemini API when AI is enabled."
                  />
                  {uploading && (
                    <p className="mt-2 text-xs font-medium text-[#0052ff]">
                      Parsing resume content and staging profile updates...
                    </p>
                  )}
                  {resumeWarnings.length > 0 && (
                    <div className="mt-4 rounded-xl border border-[#dee1e6] bg-white p-4 text-xs text-[#5b616e]">
                      <span className="font-semibold text-[#0a0b0d] block mb-1">
                        Extraction Observations:
                      </span>
                      <ul className="list-inside list-disc space-y-1 text-[#7c828a]">
                        {resumeWarnings.map((warning, i) => (
                          <li key={i}>{warning}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Section 1: Personal Details */}
            {isVisible("personal") && (
              <div className="feature-card">
                <div className="flex items-center justify-between mb-6 pb-4 border-b border-[#dee1e6]">
                  <div>
                    <h2 className="title-md text-[#0a0b0d]">Personal Details</h2>
                    <p className="body-sm text-[#5b616e]">
                      Foundational contact and identity details used on every application form.
                    </p>
                  </div>
                  <span className="badge-pill !text-[11px]">Primary</span>
                </div>

                <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
                  <Field label="Full Name">
                    <input
                      value={profile.personal.full_name}
                      onChange={(e) => updatePersonal("full_name", e.target.value)}
                      placeholder="e.g. Jane Doe"
                      className="text-input"
                    />
                  </Field>

                  <Field label="Email Address">
                    <input
                      type="email"
                      value={profile.personal.email}
                      onChange={(e) => updatePersonal("email", e.target.value)}
                      placeholder="e.g. jane@example.com"
                      className="text-input"
                    />
                  </Field>

                  <Field label="First Name (override)" hint="Optional">
                    <input
                      value={profile.personal.first_name}
                      onChange={(e) => updatePersonal("first_name", e.target.value)}
                      placeholder="Defaults to first word"
                      className="text-input"
                    />
                  </Field>

                  <Field label="Last Name (override)" hint="Optional">
                    <input
                      value={profile.personal.last_name}
                      onChange={(e) => updatePersonal("last_name", e.target.value)}
                      placeholder="Defaults to remaining words"
                      className="text-input"
                    />
                  </Field>

                  <Field label="Phone Number">
                    <input
                      value={profile.personal.phone}
                      onChange={(e) => updatePersonal("phone", e.target.value)}
                      placeholder="+1 (555) 019-2834"
                      className="text-input"
                    />
                  </Field>

                  <Field label="Location / City">
                    <input
                      value={profile.personal.location}
                      onChange={(e) => updatePersonal("location", e.target.value)}
                      placeholder="City, State / Region"
                      className="text-input"
                    />
                  </Field>

                  <Field label="Country">
                    <input
                      value={profile.personal.country}
                      onChange={(e) => updatePersonal("country", e.target.value)}
                      placeholder="e.g. United States"
                      className="text-input"
                    />
                  </Field>

                  <Field label="LinkedIn Profile">
                    <input
                      value={profile.personal.linkedin_url}
                      onChange={(e) => updatePersonal("linkedin_url", e.target.value)}
                      placeholder="https://linkedin.com/in/username"
                      className="text-input"
                    />
                  </Field>

                  <Field label="GitHub Profile">
                    <input
                      value={profile.personal.github_url}
                      onChange={(e) => updatePersonal("github_url", e.target.value)}
                      placeholder="https://github.com/username"
                      className="text-input"
                    />
                  </Field>

                  <Field label="Portfolio / Website">
                    <input
                      value={profile.personal.website_url}
                      onChange={(e) => updatePersonal("website_url", e.target.value)}
                      placeholder="https://yourportfolio.dev"
                      className="text-input"
                    />
                  </Field>
                </div>

                <div className="mt-6 pt-5 border-t border-[#dee1e6]">
                  <Field
                    label="Work Authorization & Sponsorship Status"
                    hint="Crucial"
                  >
                    <input
                      value={profile.work_authorization}
                      onChange={(e) =>
                        setProfile({
                          ...profile,
                          work_authorization: e.target.value,
                        })
                      }
                      placeholder="e.g. Authorized to work in the US without sponsorship"
                      className="text-input"
                    />
                  </Field>
                  <p className="mt-2 text-xs text-[#7c828a]">
                    Explicit statement required. The agent fills eligibility answers only from this statement or a saved answer; it never infers them from country or location.
                  </p>
                </div>
              </div>
            )}

            {/* Section 2: Work Experience */}
            {isVisible("experience") && (
              <div className="feature-card">
                <div className="flex items-center justify-between mb-6 pb-4 border-b border-[#dee1e6]">
                  <div>
                    <h2 className="title-md text-[#0a0b0d]">Work Experience</h2>
                    <p className="body-sm text-[#5b616e]">
                      Chronological employment history used to fill Greenhouse experience blocks.
                    </p>
                  </div>
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
                    className="btn-secondary-light !min-h-[38px] !py-1.5 !px-4 text-xs"
                  >
                    + Add Experience
                  </button>
                </div>

                {profile.experience.length === 0 ? (
                  <p className="text-sm text-[#7c828a] py-6 text-center">
                    No work experience listed. Click Add Experience or parse from resume above.
                  </p>
                ) : (
                  <div className="space-y-6">
                    {profile.experience.map((exp, index) => (
                      <div
                        key={index}
                        className="rounded-2xl border border-[#dee1e6] bg-[#fafbfc] p-6 space-y-4"
                      >
                        <div className="flex items-center justify-between">
                          <span className="caption-strong text-[#0052ff]">
                            Position #{index + 1}
                          </span>
                          <button
                            onClick={() =>
                              setProfile({
                                ...profile,
                                experience: profile.experience.filter(
                                  (_, i) => i !== index
                                ),
                              })
                            }
                            className="text-xs text-[#cf202f] hover:underline"
                          >
                            Remove Position
                          </button>
                        </div>

                        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
                          <Field label="Employer">
                            <input
                              value={exp.employer}
                              onChange={(e) =>
                                updateExperience(index, { employer: e.target.value })
                              }
                              placeholder="e.g. Acme Corp"
                              className="text-input"
                            />
                          </Field>

                          <Field label="Job Title">
                            <input
                              value={exp.title}
                              onChange={(e) =>
                                updateExperience(index, { title: e.target.value })
                              }
                              placeholder="e.g. Software Engineer"
                              className="text-input"
                            />
                          </Field>

                          <Field label="Employment Dates">
                            <input
                              value={exp.dates}
                              onChange={(e) =>
                                updateExperience(index, { dates: e.target.value })
                              }
                              placeholder="e.g. Jan 2022 - Present"
                              className="text-input"
                            />
                          </Field>
                        </div>

                        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 pt-2">
                          <ListEditor
                            label="Key Responsibilities"
                            value={exp.responsibilities}
                            onChange={(next) =>
                              updateExperience(index, { responsibilities: next })
                            }
                            placeholder="Architected scalable microservices..."
                          />

                          <ListEditor
                            label="Key Achievements"
                            value={exp.achievements}
                            onChange={(next) =>
                              updateExperience(index, { achievements: next })
                            }
                            placeholder="Reduced latency by 45%..."
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Section 3: Education */}
            {isVisible("education") && (
              <div className="feature-card">
                <div className="flex items-center justify-between mb-6 pb-4 border-b border-[#dee1e6]">
                  <div>
                    <h2 className="title-md text-[#0a0b0d]">Education</h2>
                    <p className="body-sm text-[#5b616e]">
                      Academic background, degrees, and institutions.
                    </p>
                  </div>
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
                    className="btn-secondary-light !min-h-[38px] !py-1.5 !px-4 text-xs"
                  >
                    + Add Education
                  </button>
                </div>

                {profile.education.length === 0 ? (
                  <p className="text-sm text-[#7c828a] py-6 text-center">
                    No education records listed. Click Add Education or parse from resume above.
                  </p>
                ) : (
                  <div className="space-y-6">
                    {profile.education.map((edu, index) => (
                      <div
                        key={index}
                        className="rounded-2xl border border-[#dee1e6] bg-[#fafbfc] p-6 space-y-4"
                      >
                        <div className="flex items-center justify-between">
                          <span className="caption-strong text-[#0052ff]">
                            Education #{index + 1}
                          </span>
                          <button
                            onClick={() =>
                              setProfile({
                                ...profile,
                                education: profile.education.filter(
                                  (_, i) => i !== index
                                ),
                              })
                            }
                            className="text-xs text-[#cf202f] hover:underline"
                          >
                            Remove Record
                          </button>
                        </div>

                        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                          <Field label="Institution / University">
                            <input
                              value={edu.institution}
                              onChange={(e) =>
                                updateEducation(index, { institution: e.target.value })
                              }
                              placeholder="e.g. Stanford University"
                              className="text-input"
                            />
                          </Field>

                          <Field label="Degree">
                            <input
                              value={edu.degree}
                              onChange={(e) =>
                                updateEducation(index, { degree: e.target.value })
                              }
                              placeholder="e.g. Bachelor of Science"
                              className="text-input"
                            />
                          </Field>

                          <Field label="Field of Study">
                            <input
                              value={edu.field_of_study}
                              onChange={(e) =>
                                updateEducation(index, {
                                  field_of_study: e.target.value,
                                })
                              }
                              placeholder="e.g. Computer Science"
                              className="text-input"
                            />
                          </Field>

                          <div className="grid grid-cols-2 gap-3">
                            <Field label="GPA" hint="Optional">
                              <input
                                value={edu.gpa ?? ""}
                                onChange={(e) =>
                                  updateEducation(index, { gpa: e.target.value })
                                }
                                placeholder="e.g. 3.8"
                                className="text-input"
                              />
                            </Field>

                            <Field label="Attendance Dates">
                              <input
                                value={edu.dates}
                                onChange={(e) =>
                                  updateEducation(index, { dates: e.target.value })
                                }
                                placeholder="e.g. 2018 - 2022"
                                className="text-input"
                              />
                            </Field>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Section 4: Skills & Projects */}
            {isVisible("skills") && (
              <div className="feature-card">
                <div className="mb-6 pb-4 border-b border-[#dee1e6]">
                  <h2 className="title-md text-[#0a0b0d]">Skills & Projects</h2>
                  <p className="body-sm text-[#5b616e]">
                    Core competencies and highlighted projects used during contextual matching.
                  </p>
                </div>

                <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
                  <ListEditor
                    label="Core Skills"
                    value={profile.skills}
                    onChange={(next) => setProfile({ ...profile, skills: next })}
                    placeholder="TypeScript&#10;Python&#10;React&#10;PostgreSQL"
                    rows={6}
                  />

                  <ListEditor
                    label="Highlighted Projects"
                    value={profile.projects}
                    onChange={(next) => setProfile({ ...profile, projects: next })}
                    placeholder="Algorithmic Trading Bot&#10;Automated Form Filling Assistant"
                    rows={6}
                  />
                </div>
              </div>
            )}

            {/* Section 5: Documents & Cover Letter */}
            {isVisible("documents") && (
              <div className="feature-card">
                <div className="mb-6 pb-4 border-b border-[#dee1e6]">
                  <h2 className="title-md text-[#0a0b0d]">Documents & Cover Letter</h2>
                  <p className="body-sm text-[#5b616e]">
                    Direct file references and reusable cover letter template.
                  </p>
                </div>

                <div className="space-y-6">
                  <div>
                    <Field label="Active Resume Storage Path">
                      <input
                        value={profile.resume_path}
                        onChange={(e) =>
                          setProfile({ ...profile, resume_path: e.target.value })
                        }
                        placeholder="backend/uploads/resume.pdf"
                        className="text-input font-mono text-xs"
                      />
                    </Field>
                    <p className="mt-2 text-xs text-[#7c828a]">
                      Uploaded resumes are stored in backend/uploads and linked automatically.
                    </p>
                  </div>

                  <div className="pt-4 border-t border-[#dee1e6]">
                    <div className="flex items-center justify-between mb-3">
                      <label className="block text-xs font-semibold uppercase tracking-wider text-[#5b616e]">
                        Cover Letter File Attachment
                      </label>
                      <span className="badge-pill !text-[11px]">Optional</span>
                    </div>
                    <FilePicker
                      accept=".pdf,.doc,.docx,.txt,.rtf"
                      buttonLabel={
                        profile.cover_letter_path
                          ? "Replace Letter"
                          : "Attach Letter File"
                      }
                      selectedName={fileName(profile.cover_letter_path)}
                      onSelect={handleCoverLetterUpload}
                      disabled={uploadingCoverLetter}
                      helpText="Upload a file to store it in backend/uploads and extract its text below."
                    />
                    {coverLetterWarnings.length > 0 && (
                      <div className="mt-3 rounded-xl border border-[#dee1e6] bg-[#fafbfc] p-3 text-xs text-[#5b616e]">
                        <ul className="list-inside list-disc space-y-1 text-[#7c828a]">
                          {coverLetterWarnings.map((warning, i) => (
                            <li key={i}>{warning}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>

                  <div className="pt-4 border-t border-[#dee1e6]">
                    <Field label="Default Cover Letter Text">
                      <textarea
                        value={profile.cover_letter}
                        onChange={(e) =>
                          setProfile({ ...profile, cover_letter: e.target.value })
                        }
                        rows={7}
                        placeholder="Dear Hiring Team, I am writing to express my strong enthusiasm for this role..."
                        className="text-input resize-y !h-auto min-h-[140px]"
                      />
                    </Field>
                    <p className="mt-2 text-xs text-[#7c828a]">
                      Filled into Greenhouse free-form cover letter input fields.
                    </p>
                  </div>
                </div>
              </div>
            )}

            {/* Section 6: Saved Answers */}
            {isVisible("saved-answers") && (
              <div className="feature-card">
                <div className="mb-6 pb-4 border-b border-[#dee1e6]">
                  <h2 className="title-md text-[#0a0b0d]">Approved Saved Answers</h2>
                  <p className="body-sm text-[#5b616e]">
                    Pre-approved responses to custom questions. The agent only reuses answers explicitly saved here.
                  </p>
                </div>

                {Object.entries(profile.saved_answers).length === 0 ? (
                  <p className="text-sm text-[#7c828a] py-6 text-center">
                    No approved answers saved yet. Add common employer questions below.
                  </p>
                ) : (
                  <div className="space-y-3 mb-6">
                    {Object.entries(profile.saved_answers).map(([key, value]) => (
                      <div
                        key={key}
                        className="rounded-2xl border border-[#dee1e6] bg-[#fafbfc] p-4 flex flex-col gap-2"
                      >
                        <div className="flex items-center justify-between">
                          <span className="text-sm font-semibold text-[#0a0b0d]">
                            {key}
                          </span>
                          <button
                            onClick={() => removeSavedAnswer(key)}
                            className="text-xs text-[#cf202f] hover:underline"
                          >
                            Remove
                          </button>
                        </div>
                        <input
                          value={value}
                          onChange={(e) =>
                            setProfile({
                              ...profile,
                              saved_answers: {
                                ...profile.saved_answers,
                                [key]: e.target.value,
                              },
                            })
                          }
                          className="text-input !bg-white"
                        />
                      </div>
                    ))}
                  </div>
                )}

                {/* Add Answer Form */}
                <div className="rounded-2xl border border-[#dee1e6] bg-[#f7f7f7] p-5">
                  <span className="caption-strong text-[#5b616e] block mb-3">
                    + Add New Approved Answer
                  </span>
                  <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                    <Field label="Question Keyword / Pattern">
                      <input
                        value={newAnswerKey}
                        onChange={(e) => setNewAnswerKey(e.target.value)}
                        placeholder="e.g. Are you willing to relocate?"
                        className="text-input"
                      />
                    </Field>
                    <Field label="Approved Response">
                      <input
                        value={newAnswerValue}
                        onChange={(e) => setNewAnswerValue(e.target.value)}
                        placeholder="e.g. Yes, willing to relocate."
                        className="text-input"
                      />
                    </Field>
                  </div>
                  <div className="mt-4">
                    <button
                      onClick={addSavedAnswer}
                      disabled={!newAnswerKey.trim()}
                      className="btn-secondary-light !min-h-[40px] text-xs"
                    >
                      Save Answer Pattern
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </section>

      {/* Floating Bottom Sticky Action Dock */}
      <div className="fixed bottom-0 left-0 right-0 z-40 border-t border-[#dee1e6] bg-white/95 backdrop-blur-md py-4 shadow-lg">
        <div className="content-container flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="h-2 w-2 rounded-full bg-[#05b169]" />
            <span className="text-xs text-[#5b616e] hidden sm:inline">
              Changes stay local to your machine (backend/profile.json)
            </span>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={handleSave}
              disabled={saving}
              className="btn-primary !min-h-[48px] !px-8 text-sm"
            >
              {saving ? "Writing to Disk..." : "Save Candidate Profile"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
