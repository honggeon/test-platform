/**
 * 版权所有 (c) 2023-2026 北京慧测信息技术有限公司(但问智能) 保留所有权利。
 * 
 * 本代码版权归北京慧测信息技术有限公司(但问智能)所有，仅用于学习交流目的，未经公司商业授权，
 * 不得用于任何商业用途，包括但不限于商业环境部署、售卖或以任何形式进行商业获利。违者必究。
 * 
 * 授权商业应用请联系微信：huice666
 */

/**
 * 文档上传 API
 */

import { t } from "@/lib/translations";

export interface DocumentUploadResponse {
  success: boolean;
  data: {
    object_name: string;
    file_name: string;
    file_size: number;
    content_type: string;
    url: string;
  };
}

/**
 * 上传文档到 MinIO
 */
export async function uploadDocument(file: File): Promise<DocumentUploadResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch("/api/v2/documents/upload", {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || t("common.uploadFailed"));
  }

  return response.json();
}

