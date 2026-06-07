/**
 * 版权所有 (c) 2023-2026 北京慧测信息技术有限公司(但问智能) 保留所有权利。
 * 
 * 本代码版权归北京慧测信息技术有限公司(但问智能)所有，仅用于学习交流目的，未经公司商业授权，
 * 不得用于任何商业用途，包括但不限于商业环境部署、售卖或以任何形式进行商业获利。违者必究。
 * 
 * 授权商业应用请联系微信：huice666
 */

"use client";

import React, { useCallback } from "react";
import { useStream } from "@langchain/langgraph-sdk/react";
import {
  type Message,
  type Assistant,
  type Checkpoint,
} from "@langchain/langgraph-sdk";
import { v4 as uuidv4 } from "uuid";
import type { UseStreamThread } from "@langchain/langgraph-sdk/react";
import type { TodoItem } from "@/lib/langgraph/types";
import { useClient } from "@/providers/ClientProvider";
import { useQueryState } from "nuqs";

export type StateType = {
  messages: Message[];
  todos: TodoItem[];
  files: Record<string, string>;
  email?: {
    id?: string;
    subject?: string;
    page_content?: string;
  };
  ui?: any;
  context?: {
    project_identifier?: string;
    folder_id?: string;
    template_type?: string;
  };
};

export function useChat({
  activeAssistant,
  onHistoryRevalidate,
  thread,
  onTestCaseCreated,
}: {
  activeAssistant: Assistant | null;
  onHistoryRevalidate?: () => void;
  thread?: UseStreamThread<StateType>;
  onTestCaseCreated?: () => void;
}) {
  const [threadId, setThreadId] = useQueryState("threadId");
  const [assistantId, setAssistantId] = useQueryState("assistantId");
  const client = useClient();

  // 同步 assistantId 到 URL
  React.useEffect(() => {
    if (activeAssistant?.assistant_id && assistantId !== activeAssistant.assistant_id) {
      setAssistantId(activeAssistant.assistant_id);
    }
  }, [activeAssistant?.assistant_id, assistantId, setAssistantId]);

  // 处理流完成事件
  const handleFinish = useCallback(() => {
    onHistoryRevalidate?.();
    // 检测是否创建了测试用例（通过检查最后的消息中是否包含工具调用）
    onTestCaseCreated?.();
  }, [onHistoryRevalidate, onTestCaseCreated]);

  const stream = useStream<StateType>({
    assistantId: activeAssistant?.assistant_id || "",
    client: client ?? undefined,
    reconnectOnMount: true,
    threadId: threadId ?? null,
    onThreadId: setThreadId,
    defaultHeaders: { "x-auth-scheme": "langsmith" },
    // deepagents subagent checkpoint 与 history 回放存在兼容问题，关闭以避免 500
    fetchStateHistory: false,
    // Revalidate thread list when stream finishes, errors, or creates new thread
    onFinish: handleFinish,
    onError: onHistoryRevalidate,
    onCreated: onHistoryRevalidate,
    ...(thread ? { thread } : {}),
  });

  const sendMessage = useCallback(
    (content: string) => {
      const newMessage: Message = { id: uuidv4(), type: "human", content };

      // 从 assistant config 中提取 context 信息
      const context = activeAssistant?.config?.configurable || {};

      // 构建 context 对象
      const agentContext: Record<string, any> = {
        project_identifier: context.project_identifier || "",
        folder_id: context.folder_id || "",
        template_type: context.template_type || "test_case",
      };

      stream.submit(
        {
          messages: [newMessage],
          // 将 context 信息传递给后端智能体
          context: agentContext
        },
        {
          optimisticValues: (prev) => ({
            messages: [...(prev.messages ?? []), newMessage],
          }),
          config: { ...(activeAssistant?.config ?? {}), recursion_limit: 1000 },
        }
      );
      // Update thread list immediately when sending a message
      onHistoryRevalidate?.();
    },
    [stream, activeAssistant?.config, onHistoryRevalidate]
  );

  const runSingleStep = useCallback(
    (
      messages: Message[],
      checkpoint?: Checkpoint,
      isRerunningSubagent?: boolean,
      optimisticMessages?: Message[]
    ) => {
      if (checkpoint) {
        stream.submit(undefined, {
          ...(optimisticMessages
            ? { optimisticValues: { messages: optimisticMessages } }
            : {}),
          config: activeAssistant?.config,
          checkpoint: checkpoint,
          ...(isRerunningSubagent
            ? { interruptAfter: ["tools"] }
            : { interruptBefore: ["tools"] }),
        });
      } else {
        stream.submit(
          { messages },
          { config: activeAssistant?.config, interruptBefore: ["tools"] }
        );
      }
    },
    [stream, activeAssistant?.config]
  );

  const setFiles = useCallback(
    async (files: Record<string, string>) => {
      if (!threadId) return;
      // TODO: missing a way how to revalidate the internal state
      // I think we do want to have the ability to externally manage the state
      await client.threads.updateState(threadId, { values: { files } });
    },
    [client, threadId]
  );

  const continueStream = useCallback(
    (hasTaskToolCall?: boolean) => {
      stream.submit(undefined, {
        config: {
          ...(activeAssistant?.config || {}),
          recursion_limit: 1000,
        },
        ...(hasTaskToolCall
          ? { interruptAfter: ["tools"] }
          : { interruptBefore: ["tools"] }),
      });
      // Update thread list when continuing stream
      onHistoryRevalidate?.();
    },
    [stream, activeAssistant?.config, onHistoryRevalidate]
  );

  const markCurrentThreadAsResolved = useCallback(() => {
    stream.submit(null, { command: { goto: "__end__", update: null } });
    // Update thread list when marking thread as resolved
    onHistoryRevalidate?.();
  }, [stream, onHistoryRevalidate]);

  const resumeInterrupt = useCallback(
    (value: any) => {
      stream.submit(null, { command: { resume: value } });
      // Update thread list when resuming from interrupt
      onHistoryRevalidate?.();
    },
    [stream, onHistoryRevalidate]
  );

  const stopStream = useCallback(() => {
    stream.stop();
  }, [stream]);

  return {
    stream,
    todos: stream.values.todos ?? [],
    files: stream.values.files ?? {},
    email: stream.values.email,
    ui: stream.values.ui,
    setFiles,
    messages: stream.messages,
    isLoading: stream.isLoading,
    isThreadLoading: stream.isThreadLoading,
    interrupt: stream.interrupt,
    getMessagesMetadata: stream.getMessagesMetadata,
    sendMessage,
    runSingleStep,
    continueStream,
    stopStream,
    markCurrentThreadAsResolved,
    resumeInterrupt,
  };
}
