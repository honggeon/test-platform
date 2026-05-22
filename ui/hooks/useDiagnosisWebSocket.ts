"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type {
  WSServerMessage,
  WSDiagnosisCompletedPayload,
  WSUnreadReportsPayload,
} from "@/types/diagnosis";

interface UseDiagnosisWebSocketOptions {
  projectId: string | null;
  onDiagnosisCompleted?: (payload: WSDiagnosisCompletedPayload) => void;
  onUnreadReports?: (payload: WSUnreadReportsPayload) => void;
  enabled?: boolean;
}

interface UseDiagnosisWebSocketReturn {
  connected: boolean;
  unreadReports: WSDiagnosisCompletedPayload[];
  ackReport: (reportId: string) => void;
  clearUnread: () => void;
}

const WS_BASE_URL = "ws://localhost:8000";
const PING_INTERVAL = 30000;
const RECONNECT_DELAY = 3000;
const ACK_TIMEOUT = 3000;

export function useDiagnosisWebSocket({
  projectId,
  onDiagnosisCompleted,
  onUnreadReports,
  enabled = true,
}: UseDiagnosisWebSocketOptions): UseDiagnosisWebSocketReturn {
  const [connected, setConnected] = useState(false);
  const [unreadReports, setUnreadReports] = useState<WSDiagnosisCompletedPayload[]>([]);

  const wsRef = useRef<WebSocket | null>(null);
  const pingTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const ackTimersRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());
  const shouldReconnectRef = useRef(true);

  const cleanup = useCallback(() => {
    shouldReconnectRef.current = false;

    if (pingTimerRef.current) {
      clearInterval(pingTimerRef.current);
      pingTimerRef.current = null;
    }
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    ackTimersRef.current.forEach((timer) => clearTimeout(timer));
    ackTimersRef.current.clear();

    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
  }, []);

  const sendAck = useCallback((ws: WebSocket, reportId: string) => {
    if (ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "ack", report_id: reportId }));
    }
  }, []);

  const ackReport = useCallback(
    (reportId: string) => {
      if (wsRef.current) {
        sendAck(wsRef.current, reportId);
      }
      setUnreadReports((prev) =>
        prev.filter((r) => r.report_id !== reportId)
      );
      // 清除对应的 ack timer
      const timer = ackTimersRef.current.get(reportId);
      if (timer) {
        clearTimeout(timer);
        ackTimersRef.current.delete(reportId);
      }
    },
    [sendAck]
  );

  const clearUnread = useCallback(() => {
    unreadReports.forEach((r) => {
      if (wsRef.current) {
        sendAck(wsRef.current, r.report_id);
      }
    });
    ackTimersRef.current.forEach((timer) => clearTimeout(timer));
    ackTimersRef.current.clear();
    setUnreadReports([]);
  }, [unreadReports, sendAck]);

  const connect = useCallback(() => {
    if (!projectId || !enabled) return;

    // 避免重复连接
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    shouldReconnectRef.current = true;

    try {
      const wsUrl = `${WS_BASE_URL}/ws/diagnosis/${projectId}`;
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        setConnected(true);
        // 启动心跳
        pingTimerRef.current = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: "pong" }));
          }
        }, PING_INTERVAL);
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data) as WSServerMessage;

          if (data.type === "ping") {
            // 服务器 ping，回复 pong
            if (ws.readyState === WebSocket.OPEN) {
              ws.send(JSON.stringify({ type: "pong" }));
            }
            return;
          }

          if (data.type === "unread_reports") {
            const payload = data as WSUnreadReportsPayload;
            setUnreadReports((prev) => {
              const existingIds = new Set(prev.map((r) => r.report_id));
              const newReports = payload.reports.filter(
                (r) => !existingIds.has(r.report_id)
              );
              return [...prev, ...newReports];
            });
            onUnreadReports?.(payload);
            return;
          }

          if (
            data.type === "diagnosis_completed" ||
            data.type === "diagnosis_completed_replay"
          ) {
            const payload = data as WSDiagnosisCompletedPayload;

            // 添加到 unread 队列，启动 ack 超时
            setUnreadReports((prev) => {
              if (prev.some((r) => r.report_id === payload.report_id)) {
                return prev;
              }
              return [...prev, payload];
            });

            // 设置 ack 超时：3s 内未 ack 则保留在 unread 中
            const timer = setTimeout(() => {
              // 超时后不做任何事，报告继续留在 unread 中
              ackTimersRef.current.delete(payload.report_id);
            }, ACK_TIMEOUT);
            ackTimersRef.current.set(payload.report_id, timer);

            // 发送 ack
            sendAck(ws, payload.report_id);

            onDiagnosisCompleted?.(payload);
          }
        } catch {
          // 忽略解析失败的消息
        }
      };

      ws.onclose = () => {
        setConnected(false);
        if (pingTimerRef.current) {
          clearInterval(pingTimerRef.current);
          pingTimerRef.current = null;
        }
        // 自动重连
        if (shouldReconnectRef.current) {
          reconnectTimerRef.current = setTimeout(() => {
            connect();
          }, RECONNECT_DELAY);
        }
      };

      ws.onerror = () => {
        // 错误时让 onclose 处理重连
        ws.close();
      };
    } catch {
      // 连接失败，延迟重试
      reconnectTimerRef.current = setTimeout(() => {
        if (shouldReconnectRef.current) {
          connect();
        }
      }, RECONNECT_DELAY);
    }
  }, [projectId, enabled, onDiagnosisCompleted, onUnreadReports, sendAck]);

  useEffect(() => {
    if (enabled && projectId) {
      connect();
    }
    return () => {
      cleanup();
    };
  }, [projectId, enabled, connect, cleanup]);

  return {
    connected,
    unreadReports,
    ackReport,
    clearUnread,
  };
}
