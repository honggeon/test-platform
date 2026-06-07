/**
 * 认证 API 与本地存储
 */

export interface UserResponse {
  id: string;
  username: string;
  email: string;
  display_name: string | null;
  is_active: boolean;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: UserResponse;
}

export interface UserRegister {
  username: string;
  email: string;
  password: string;
  display_name?: string;
}

export interface UserLogin {
  username: string;
  password: string;
}

const AUTH_TOKEN_KEY = "access_token";
const AUTH_USER_KEY = "auth_user";
const AUTH_COOKIE = "access_token";

function getAuthApiBase(): string {
  const configured = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "");
  if (
    configured &&
    (configured.startsWith("http://") || configured.startsWith("https://"))
  ) {
    return configured;
  }
  if (typeof window !== "undefined") {
    return window.location.origin;
  }
  return "http://localhost:8000";
}

export function getAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(AUTH_TOKEN_KEY);
}

export function getStoredUser(): UserResponse | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem(AUTH_USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as UserResponse;
  } catch {
    return null;
  }
}

export function saveAuthSession(data: TokenResponse): void {
  localStorage.setItem(AUTH_TOKEN_KEY, data.access_token);
  localStorage.setItem(AUTH_USER_KEY, JSON.stringify(data.user));
  document.cookie = `${AUTH_COOKIE}=${encodeURIComponent(data.access_token)}; path=/; max-age=${data.expires_in}; SameSite=Lax`;
}

export function clearAuthSession(): void {
  localStorage.removeItem(AUTH_TOKEN_KEY);
  localStorage.removeItem(AUTH_USER_KEY);
  document.cookie = `${AUTH_COOKIE}=; path=/; max-age=0; SameSite=Lax`;
}

export function getAuthHeaders(): Record<string, string> {
  const token = getAccessToken();
  if (!token) return {};
  return { Authorization: `Bearer ${token}` };
}

async function parseError(response: Response): Promise<string> {
  try {
    const data = await response.json();
    if (typeof data?.detail === "string") return data.detail;
    if (typeof data?.message === "string") return data.message;
    if (Array.isArray(data?.detail)) {
      return data.detail.map((d: { msg?: string }) => d.msg || "").join("; ");
    }
  } catch {
    // ignore
  }
  return `HTTP ${response.status}`;
}

export async function registerUser(data: UserRegister): Promise<UserResponse> {
  const response = await fetch(`${getAuthApiBase()}/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return response.json();
}

export async function loginUser(data: UserLogin): Promise<TokenResponse> {
  const response = await fetch(`${getAuthApiBase()}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  const tokenData: TokenResponse = await response.json();
  saveAuthSession(tokenData);
  return tokenData;
}

export function logoutUser(): void {
  clearAuthSession();
}
