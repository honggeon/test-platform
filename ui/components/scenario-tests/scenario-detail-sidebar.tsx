"use client";

import * as React from "react";
import { X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { apiClient } from "@/lib/api/client";

interface ScenarioDetailSidebarProps {
  scenarioId: string;
  projectId: string;
  onClose: () => void;
  onScenarioUpdated: () => void;
  onOpenAIChat?: (prompt: string) => void;
  onSwitchToMonitor?: () => void;
}

interface Scenario {
  id: string;
  name: string;
  description: string | null;
  status: string;
  steps?: ScenarioStep[];
}

interface ScenarioStep {
  id: string;
  name: string;
  endpoint_id: string;
  method: string;
  path: string;
  sort_order: number;
}

export function ScenarioDetailSidebar({
  scenarioId,
  projectId,
  onClose,
  onScenarioUpdated,
  onOpenAIChat,
  onSwitchToMonitor,
}: ScenarioDetailSidebarProps) {
  const [scenario, setScenario] = React.useState<Scenario | null>(null);
  const [loading, setLoading] = React.useState(true);

  React.useEffect(() => {
    setLoading(true);
    apiClient
      .get<{ success: boolean; data: Scenario }>(
        `/projects/${projectId}/scenarios/${scenarioId}`
      )
      .then((res) => {
        if (res.success) setScenario(res.data);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [projectId, scenarioId]);

  if (loading) {
    return (
      <div className="h-full p-4">
        <p className="text-sm text-muted-foreground">加载中...</p>
      </div>
    );
  }

  if (!scenario) {
    return (
      <div className="h-full p-4">
        <p className="text-sm text-muted-foreground">场景未找到</p>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b px-4 py-3">
        <h3 className="font-medium text-sm truncate">{scenario.name}</h3>
        <div className="flex items-center gap-1">
          {onSwitchToMonitor && (
            <Button variant="outline" size="sm" className="h-7 text-xs" onClick={onSwitchToMonitor}>
              监视
            </Button>
          )}
          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>
      </div>

      <ScrollArea className="flex-1 p-4">
        {scenario.description && (
          <p className="text-sm text-muted-foreground mb-4">{scenario.description}</p>
        )}

        <div className="flex items-center gap-2 mb-4">
          <Badge variant="outline">{scenario.status || "draft"}</Badge>
        </div>

        <h4 className="text-sm font-medium mb-2">步骤 ({scenario.steps?.length || 0})</h4>
        <div className="space-y-2">
          {scenario.steps?.map((step, i) => (
            <div key={step.id} className="rounded border p-3 text-xs">
              <div className="flex items-center gap-2">
                <span className="text-muted-foreground">{i + 1}.</span>
                <Badge variant="secondary" className="text-[10px]">
                  {step.method || "GET"}
                </Badge>
                <span className="font-medium truncate">{step.name}</span>
              </div>
              <p className="mt-1 text-muted-foreground truncate">{step.path}</p>
            </div>
          ))}
        </div>
      </ScrollArea>
    </div>
  );
}
