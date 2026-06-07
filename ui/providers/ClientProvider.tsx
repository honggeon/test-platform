/**
 * 版权所有 (c) 2023-2026 北京慧测信息技术有限公司(但问智能) 保留所有权利。
 * 
 * 本代码版权归北京慧测信息技术有限公司(但问智能)所有，仅用于学习交流目的，未经公司商业授权，
 * 不得用于任何商业用途，包括但不限于商业环境部署、售卖或以任何形式进行商业获利。违者必究。
 * 
 * 授权商业应用请联系微信：huice666
 */

"use client";

import { createContext, useContext, useMemo, ReactNode } from "react";
import { Client } from "@langchain/langgraph-sdk";
import { getAuthHeaders } from "@/lib/auth";
import { getDeploymentUrl } from "@/lib/langgraph/config";

interface ClientContextValue {
  client: Client;
}

const ClientContext = createContext<ClientContextValue | null>(null);

interface ClientProviderProps {
  children: ReactNode;
  apiKey: string;
}

export function ClientProvider({
  children,
  apiKey,
}: ClientProviderProps) {
  const client = useMemo(() => {
    const deploymentUrl = getDeploymentUrl();
    return new Client({
      apiUrl: deploymentUrl,
      defaultHeaders: {
        "Content-Type": "application/json",
        "X-Api-Key": apiKey,
        ...getAuthHeaders(),
      },
    });
  }, [apiKey]);

  const value = useMemo(() => ({ client }), [client]);

  return (
    <ClientContext.Provider value={value}>{children}</ClientContext.Provider>
  );
}

export function useClient(): Client {
  const context = useContext(ClientContext);

  if (!context) {
    throw new Error("useClient must be used within a ClientProvider");
  }
  return context.client;
}
