export type ApiErrorDetail = {
  field: string;
  message: string;
  reason: string;
};

type ApiErrorPayload = {
  error?: {
    code?: unknown;
    details?: unknown;
    message?: unknown;
  };
  meta?: {
    request_id?: unknown;
  };
  status?: unknown;
};

const DEFAULT_ERROR_CODE = 'INTERNAL_SERVER_ERROR';
const DEFAULT_ERROR_MESSAGE = '요청을 처리하지 못했습니다.';

export class ApiRequestError extends Error {
  readonly code: string;
  readonly details: ApiErrorDetail[];
  readonly requestId: string | null;

  constructor({
    code,
    details,
    message,
    requestId,
  }: {
    code: string;
    details: ApiErrorDetail[];
    message: string;
    requestId: string | null;
  }) {
    super(message);
    this.name = 'ApiRequestError';
    this.code = code;
    this.details = details;
    this.requestId = requestId;
  }
}

const isErrorDetail = (value: unknown): value is ApiErrorDetail => {
  if (!value || typeof value !== 'object') return false;
  const detail = value as Record<string, unknown>;
  return (
    typeof detail.field === 'string' &&
    typeof detail.reason === 'string' &&
    typeof detail.message === 'string'
  );
};

const parseApiError = async (response: Response): Promise<ApiRequestError> => {
  const headerRequestId = response.headers.get('X-Request-ID');
  try {
    const payload = (await response.json()) as ApiErrorPayload;
    const details = Array.isArray(payload.error?.details)
      ? payload.error.details.filter(isErrorDetail)
      : [];
    const requestId =
      typeof payload.meta?.request_id === 'string'
        ? payload.meta.request_id
        : headerRequestId;
    return new ApiRequestError({
      code:
        typeof payload.error?.code === 'string'
          ? payload.error.code
          : DEFAULT_ERROR_CODE,
      details,
      message:
        typeof payload.error?.message === 'string'
          ? payload.error.message
          : DEFAULT_ERROR_MESSAGE,
      requestId,
    });
  } catch {
    return new ApiRequestError({
      code: DEFAULT_ERROR_CODE,
      details: [],
      message: DEFAULT_ERROR_MESSAGE,
      requestId: headerRequestId,
    });
  }
};

export const requestJson = async <ResponseData>(
  input: string,
  init?: RequestInit,
): Promise<ResponseData> => {
  const response = await fetch(input, init);
  if (!response.ok) throw await parseApiError(response);
  return (await response.json()) as ResponseData;
};
