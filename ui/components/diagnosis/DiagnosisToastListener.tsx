"use client";

import { useCallback } from "react";
import { usePathname, useRouter } from "next/navigation";
import { toast } from "sonner";
import { useDiagnosisWebSocket } from "@/hooks/useDiagnosisWebSocket";
import type { WSDiagnosisCompletedPayload } from "@/types/diagnosis";

/**
 * 全局诊断 WebSocket 通知监听器
 * 挂载在 layout 中，自动监听当前项目的诊断完成事件并弹出 toast
 */
export function DiagnosisToastListener() {
  const pathname = usePathname();
  const router = useRouter();

  // 从 URL 中提取 projectId
  const projectId = (() => {
    const match = pathname.match(/\/projects\/([^/]+)/);
    return match ? match[1] : null;
  })();

  const handleCompleted = useCallback(
    (payload: WSDiagnosisCompletedPayload) => {
      const total = payload.summary?.total_failures ?? 0;
      toast.success("诊断分析完成", {
        description: `发现 ${total} 个失败，报告 ID: ${payload.report_id.slice(0, 8)}`,
        action: {
          label: "查看",
          onClick: () => {
            if (projectId) {
              router.push(`/projects/${projectId}/diagnosis`);
            }
          },
        },
        duration: 8000,
      });
    },
    [projectId, router]
  );

  // 仅在项目页面启用 WebSocket
  const enabled = !!projectId;

  useDiagnosisWebSocket({
    projectId,
    onDiagnosisCompleted: handleCompleted,
    enabled,
  });

  return null;
}
