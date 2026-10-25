export const backendUrl =
  process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

export class ApiError extends Error {
  status: number;

  constructor(message: string, status = 0) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

type Envelope<T> = { status: string; data: T; message?: string };

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;

  try {
    response = await fetch(`${backendUrl}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(init?.headers ?? {}),
      },
    });
  } catch {
    throw new ApiError(
      `Cannot reach the backend at ${backendUrl}. Make sure it is running.`
    );
  }

  const text = await response.text();
  let payload: { detail?: unknown; message?: unknown } | null = null;
  try {
    payload = text ? JSON.parse(text) : null;
  } catch {
    payload = null;
  }

  if (!response.ok) {
    const detail = payload?.detail ?? payload?.message ?? response.statusText;
    throw new ApiError(
      typeof detail === "string" ? detail : JSON.stringify(detail),
      response.status
    );
  }

  return payload as T;
}

// ---- Types ----

export interface PersonalDetails {
  full_name: string;
  first_name: string;
  last_name: string;
  email: string;
  phone: string;
  location: string;
  country: string;
  linkedin_url: string;
  github_url: string;
  website_url: string;
}

export interface Education {
  institution: string;
  degree: string;
  field_of_study: string;
  dates: string;
  gpa: string | null;
}

export interface Experience {
  employer: string;
  title: string;
  dates: string;
  responsibilities: string[];
  achievements: string[];
}

export interface Profile {
  personal: PersonalDetails;
  education: Education[];
  experience: Experience[];
  skills: string[];
  projects: string[];
  resume_path: string;
  cover_letter: string;
  cover_letter_path: string;
  work_authorization: string;
  saved_answers: Record<string, string>;
}

export interface HealthStatus {
  status: string;
  auto_submit: boolean;
  ai_enabled: boolean;
  ai_provider: string;
  ai_model: string;
}

export type ResumeExtractedProfile = Pick<
  Profile,
  "personal" | "education" | "experience" | "skills" | "projects"
>;

export interface ResumePrefillResult {
  status: string;
  message: string;
  resume_path: string;
  profile: ResumeExtractedProfile;
  fields_found: number;
  warnings: string[];
  ai_used: boolean;
  text_chars: number;
}

export interface ApplicationEvent {
  id: number;
  event_type: string;
  message: string;
  created_at: string;
}

export interface ReviewItem {
  id: number;
  field_name: string;
  reason: string;
  suggested_value: string | null;
  user_resolution: string | null;
  resolved_at: string | null;
}

export interface Application {
  id: number;
  job_url: string;
  company: string;
  role: string;
  status: string;
  created_at: string;
  updated_at: string;
  submitted_at: string | null;
  last_error: string | null;
  submission_attempted_at: string | null;
  submission_outcome: string | null;
}

export interface ApplicationDetail extends Application {
  confirmation_details: string | null;
  events: ApplicationEvent[];
  review_items: ReviewItem[];
}

export const emptyProfile: Profile = {
  personal: {
    full_name: "",
    first_name: "",
    last_name: "",
    email: "",
    phone: "",
    location: "",
    country: "",
    linkedin_url: "",
    github_url: "",
    website_url: "",
  },
  education: [],
  experience: [],
  skills: [],
  projects: [],
  resume_path: "",
  cover_letter: "",
  cover_letter_path: "",
  work_authorization: "",
  saved_answers: {},
};

// ---- API calls ----

export async function getHealth(): Promise<HealthStatus> {
  return request<HealthStatus>("/api/health");
}

export async function getProfile(): Promise<Profile> {
  const result = await request<Envelope<Profile>>("/api/profile");
  return result.data;
}

export async function saveProfile(profile: Profile): Promise<void> {
  await request<Envelope<null>>("/api/profile", {
    method: "PUT",
    body: JSON.stringify(profile),
  });
}

export async function uploadResume(
  filename: string,
  contentBase64: string
): Promise<string> {
  const result = await request<{ status: string; resume_path: string }>(
    "/api/profile/resume",
    {
      method: "POST",
      body: JSON.stringify({ filename, content_base64: contentBase64 }),
    }
  );
  return result.resume_path;
}

export async function prefillProfileFromResume(
  filename: string,
  contentBase64: string
): Promise<ResumePrefillResult> {
  return request<ResumePrefillResult>("/api/profile/resume/prefill", {
    method: "POST",
    body: JSON.stringify({ filename, content_base64: contentBase64 }),
  });
}

export async function uploadCoverLetter(
  filename: string,
  contentBase64: string
): Promise<{
  status: string;
  cover_letter_path: string;
  cover_letter: string;
  warnings: string[];
}> {
  return request("/api/profile/cover-letter", {
    method: "POST",
    body: JSON.stringify({ filename, content_base64: contentBase64 }),
  });
}

export async function createApplication(
  jobUrl: string,
  autoSubmit?: boolean
): Promise<{
  application_id: number;
  application_status: string;
  auto_submit: boolean;
}> {
  return request("/api/applications", {
    method: "POST",
    body: JSON.stringify({ job_url: jobUrl, auto_submit: autoSubmit }),
  });
}

export function applicationsExportUrl(): string {
  return `${backendUrl}/api/applications/export`;
}

export async function listApplications(status?: string): Promise<Application[]> {
  const query = status ? `?status=${encodeURIComponent(status)}` : "";
  const result = await request<Envelope<Application[]>>(
    `/api/applications${query}`
  );
  return result.data;
}

export async function getApplication(id: number): Promise<ApplicationDetail> {
  const result = await request<Envelope<ApplicationDetail>>(
    `/api/applications/${id}`
  );
  return result.data;
}

export async function deleteApplication(id: number): Promise<void> {
  await request(`/api/applications/${id}`, { method: "DELETE" });
}

export async function resumeApplication(
  id: number,
  autoSubmit?: boolean
): Promise<void> {
  await request(`/api/applications/${id}/resume`, {
    method: "POST",
    body: JSON.stringify({ auto_submit: autoSubmit }),
  });
}

export async function retryApplication(id: number): Promise<void> {
  await request(`/api/applications/${id}/retry`, { method: "POST" });
}

export async function resolveReviewItem(
  applicationId: number,
  itemId: number,
  resolution: string
): Promise<void> {
  await request(
    `/api/applications/${applicationId}/review-items/${itemId}/resolve`,
    {
      method: "POST",
      body: JSON.stringify({ resolution }),
    }
  );
}

export async function confirmSubmission(
  id: number,
  details: string
): Promise<void> {
  await request(`/api/applications/${id}/confirm-submission`, {
    method: "POST",
    body: JSON.stringify({ details }),
  });
}

export async function markNotSubmitted(
  id: number,
  details: string
): Promise<void> {
  await request(`/api/applications/${id}/mark-not-submitted`, {
    method: "POST",
    body: JSON.stringify({ details }),
  });
}

export function confirmationSummary(
  details: string | null
): { message: string; url?: string } | null {
  if (!details) return null;
  try {
    const parsed = JSON.parse(details) as { message?: string; url?: string };
    if (parsed.message || parsed.url) {
      return { message: parsed.message || "", url: parsed.url };
    }
  } catch {
    // Older records may contain plain text.
  }
  return { message: details };
}

// ---- UI helpers ----

export function statusClasses(status: string): string {
  switch (status) {
    case "In Progress":
      return "bg-blue-100 text-blue-800";
    case "Needs Review":
      return "bg-yellow-100 text-yellow-800";
    case "Submitted":
      return "bg-green-100 text-green-800";
    case "Failed":
      return "bg-red-100 text-red-800";
    default:
      return "bg-gray-100 text-gray-700";
  }
}

export function formatDateTime(value: string | null): string {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}
