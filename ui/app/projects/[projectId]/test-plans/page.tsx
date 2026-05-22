"use client";

import * as React from "react";
import { useParams } from "next/navigation";
import { MainLayout } from "@/components/layout";
import { Button } from "@/components/ui/button";
import { ClipboardList, Plus, Play, Trash2 } from "lucide-react";
import { apiClient } from "@/lib/api/client";

interface TestPlan {
  id: string;
  name: string;
  description: string | null;
  status: string;
  created_at: string;
}

export default function TestPlansPage() {
  const params = useParams();
  const projectId = params?.projectId as string;
  const [plans, setPlans] = React.useState<TestPlan[]>([]);
  const [loading, setLoading] = React.useState(true);

  const load = React.useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiClient.get<{ success: boolean; data: TestPlan[] }>(
        `/projects/${projectId}/test-plans`
      );
      if (res.success) setPlans(res.data || []);
    } catch {}
    setLoading(false);
  }, [projectId]);

  React.useEffect(() => { load(); }, [load]);

  const handleRun = async (id: string) => {
    try {
      await apiClient.post(`/projects/${projectId}/test-plans/${id}/execute`);
      alert("测试计划已触发执行");
    } catch {}
  };

  const handleDelete = async (id: string) => {
    try {
      await apiClient.delete(`/projects/${projectId}/test-plans/${id}`);
      await load();
    } catch {}
  };

  return (
    <MainLayout>
      <div className="p-6">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <ClipboardList className="h-5 w-5" />
            <h1 className="text-lg font-semibold">测试计划</h1>
          </div>
          <Button size="sm">
            <Plus className="mr-1 h-4 w-4" /> 新建计划
          </Button>
        </div>

        {loading ? (
          <p className="text-sm text-muted-foreground">加载中...</p>
        ) : plans.length === 0 ? (
          <p className="text-sm text-muted-foreground">暂无测试计划</p>
        ) : (
          <div className="space-y-2">
            {plans.map((plan) => (
              <div key={plan.id} className="flex items-center justify-between rounded-lg border p-4">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-sm">{plan.name}</span>
                    <span className="rounded bg-gray-100 px-1.5 py-0.5 text-[10px] text-gray-600">{plan.status}</span>
                  </div>
                  {plan.description && <p className="mt-0.5 text-xs text-muted-foreground">{plan.description}</p>}
                  <p className="text-[10px] text-muted-foreground mt-1">{plan.created_at}</p>
                </div>
                <div className="flex gap-1">
                  <Button size="icon" variant="ghost" className="h-8 w-8 text-green-600" onClick={() => handleRun(plan.id)}>
                    <Play className="h-3.5 w-3.5" />
                  </Button>
                  <Button size="icon" variant="ghost" className="h-8 w-8 text-red-500" onClick={() => handleDelete(plan.id)}>
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </MainLayout>
  );
}
