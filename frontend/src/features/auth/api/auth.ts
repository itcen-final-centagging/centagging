export type UserRole = 'USER' | 'ADMIN' | 'SUPER_ADMIN';

export type AuthenticatedUser = {
  loginId: string;
  role: UserRole;
  session: string;
  userId: number;
  userName: string;
};

export type LoginCredentials = {
  loginId: string;
  password: string;
};

type ApiUserResponse = {
  login_id: string;
  role: UserRole;
  session: string;
  user_id: number;
  user_name: string;
};

const API_BASE_URL =
  (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(
    /\/$/,
    '',
  ) ?? '';

const getErrorMessage = async (response: Response): Promise<string> => {
  try {
    const payload = (await response.json()) as { detail?: string };
    return payload.detail ?? '인증 요청을 처리하지 못했습니다.';
  } catch {
    return '인증 요청을 처리하지 못했습니다.';
  }
};

const request = async <ResponseData>(
  path: string,
  init?: RequestInit,
): Promise<ResponseData> => {
  const response = await fetch(`${API_BASE_URL}${path}`, init);
  if (!response.ok) throw new Error(await getErrorMessage(response));
  return (await response.json()) as ResponseData;
};

const toAuthenticatedUser = (response: ApiUserResponse): AuthenticatedUser => ({
  loginId: response.login_id,
  role: response.role,
  session: response.session,
  userId: response.user_id,
  userName: response.user_name,
});

export const createAuthorizationHeaders = (
  session: string,
  headers?: HeadersInit,
): Headers => {
  const authorizedHeaders = new Headers(headers);
  authorizedHeaders.set('Authorization', `Bearer ${session}`);
  return authorizedHeaders;
};

export const login = async (
  credentials: LoginCredentials,
): Promise<AuthenticatedUser> => {
  const response = await request<ApiUserResponse>('/auth/login', {
    body: JSON.stringify({
      login_id: credentials.loginId,
      password: credentials.password,
    }),
    headers: { 'Content-Type': 'application/json' },
    method: 'POST',
  });
  return toAuthenticatedUser(response);
};

export const getCurrentUser = async (
  session: string,
): Promise<AuthenticatedUser> => {
  const response = await request<ApiUserResponse>('/auth/me', {
    headers: createAuthorizationHeaders(session),
    method: 'GET',
  });
  return toAuthenticatedUser(response);
};
