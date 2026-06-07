/**
 * 版权所有 (c) 2023-2026 北京慧测信息技术有限公司(但问智能) 保留所有权利。
 * 
 * 本代码版权归北京慧测信息技术有限公司(但问智能)所有，仅用于学习交流目的，未经公司商业授权，
 * 不得用于任何商业用途，包括但不限于商业环境部署、售卖或以任何形式进行商业获利。违者必究。
 * 
 * 授权商业应用请联系微信：huice666
 */

const API_BASE_URL = "/api/v2";

interface RequestOptions extends RequestInit {
  params?: Record<string, string | number | boolean | undefined>;
}

class ApiError extends Error {
  status: number;
  data?: unknown;

  constructor(message: string, status: number, data?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.data = data;
  }
}

async function handleResponse<T>(response: Response): Promise<T> {
  const contentType = response.headers.get("content-type");
  const isJson = contentType?.includes("application/json");

  // Handle 204 No Content responses (empty body)
  if (response.status === 204) {
    if (!response.ok) {
      throw new ApiError(`HTTP error! status: ${response.status}`, response.status);
    }
    return undefined as T;
  }

  const data = isJson ? await response.json() : await response.text();

  if (!response.ok) {
    const message =
      (isJson && typeof data === 'object' && ((data as any)?.message || (data as any)?.detail)) || `HTTP error! status: ${response.status}`;
    throw new ApiError(message, response.status, data);
  }

  return data as T;
}

function buildUrl(
  path: string,
  params?: Record<string, string | number | boolean | undefined>
): string {
  const url = new URL(`${API_BASE_URL}${path}`, typeof window !== 'undefined' ? window.location.origin : 'http://localhost:3000');

  if (params) {
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null) {
        url.searchParams.append(key, String(value));
      }
    });
  }

  return url.toString();
}

export const apiClient = {
  async get<T>(path: string, options?: RequestOptions): Promise<T> {
    const url = buildUrl(path, options?.params);
    const response = await fetch(url, {
      ...options,
      method: "GET",
      headers: {
        "Content-Type": "application/json",
        ...options?.headers,
      },
    });
    return handleResponse<T>(response);
  },

  async post<T>(
    path: string,
    body?: unknown,
    options?: RequestOptions
  ): Promise<T> {
    const url = buildUrl(path, options?.params);
    const response = await fetch(url, {
      ...options,
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...options?.headers,
      },
      body: body ? JSON.stringify(body) : undefined,
    });
    return handleResponse<T>(response);
  },

  async put<T>(
    path: string,
    body?: unknown,
    options?: RequestOptions
  ): Promise<T> {
    const url = buildUrl(path, options?.params);
    const response = await fetch(url, {
      ...options,
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        ...options?.headers,
      },
      body: body ? JSON.stringify(body) : undefined,
    });
    return handleResponse<T>(response);
  },

  async patch<T>(
    path: string,
    body?: unknown,
    options?: RequestOptions
  ): Promise<T> {
    const url = buildUrl(path, options?.params);
    const response = await fetch(url, {
      ...options,
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
        ...options?.headers,
      },
      body: body ? JSON.stringify(body) : undefined,
    });
    return handleResponse<T>(response);
  },

  async delete<T>(
    path: string,
    options?: RequestOptions & { data?: unknown }
  ): Promise<T> {
    const url = buildUrl(path, options?.params);
    const { data, ...restOptions } = options || {};
    const response = await fetch(url, {
      ...restOptions,
      method: "DELETE",
      headers: {
        "Content-Type": "application/json",
        ...restOptions?.headers,
      },
      body: data ? JSON.stringify(data) : undefined,
    });
    return handleResponse<T>(response);
  },
};

export { ApiError };

