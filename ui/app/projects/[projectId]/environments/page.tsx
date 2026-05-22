"use client";

import * as React from "react";
import { useParams } from "next/navigation";
import { MainLayout } from "@/components/layout";
import { Button } from "@/components/ui/button";
import {
  getEnvironments,
  createEnvironment,
  updateEnvironment,
  deleteEnvironment,
  type TestEnvironment,
} from "@/lib/api/environments";
import {
  Plus,
  Pencil,
  Trash2,
  Server,
  Check,
  X,
} from "lucide-react";

export default function EnvironmentsPage() {
  const params = useParams();
  const projectId = params?.projectId as string;
  const [environments, setEnvironments] = React.useState<TestEnvironment[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [editing, setEditing] = React.useState<TestEnvironment | null>(null);
  const [showForm, setShowForm] = React.useState(false);
  const [form, setForm] = React.useState({ name: "", base_url: "", description: "" });

  const load = React.useCallback(async () => {
    setLoading(true);
    try {
      const res = await getEnvironments(projectId);
      if (res.success) setEnvironments(res.data || []);
    } catch {}
    setLoading(false);
  }, [projectId]);

  React.useEffect(() => { load(); }, [load]);

  const handleSave = async () => {
    try {
      if (editing) {
        await updateEnvironment(projectId, editing.id, form);
      } else {
        await createEnvironment(projectId, form);
      }
      setShowForm(false);
      setEditing(null);
      setForm({ name: "", base_url: "", description: "" });
      await load();
    } catch {}
  };

  const handleEdit = (env: TestEnvironment) => {
    setEditing(env);
    setForm({ name: env.name, base_url: env.base_url, description: env.description || "" });
    setShowForm(true);
  };

  const handleDelete = async (id: string) => {
    try {
      await deleteEnvironment(projectId, id);
      await load();
    } catch {}
  };

  return (
    <MainLayout>
      <div className="p-6">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <Server className="h-5 w-5" />
            <h1 className="text-lg font-semibold">测试环境</h1>
          </div>
          <Button size="sm" onClick={() => { setEditing(null); setForm({ name: "", base_url: "", description: "" }); setShowForm(true); }}>
            <Plus className="mr-1 h-4 w-4" /> 新建环境
          </Button>
        </div>

        {showForm && (
          <div className="mb-6 rounded-lg border p-4 space-y-3">
            <h3 className="text-sm font-medium">{editing ? "编辑环境" : "新建环境"}</h3>
            <input
              className="w-full rounded-md border px-3 py-2 text-sm"
              placeholder="环境名称"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
            <input
              className="w-full rounded-md border px-3 py-2 text-sm"
              placeholder="Base URL"
              value={form.base_url}
              onChange={(e) => setForm({ ...form, base_url: e.target.value })}
            />
            <input
              className="w-full rounded-md border px-3 py-2 text-sm"
              placeholder="描述（可选）"
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
            />
            <div className="flex gap-2">
              <Button size="sm" onClick={handleSave}><Check className="mr-1 h-3 w-3" />保存</Button>
              <Button size="sm" variant="outline" onClick={() => setShowForm(false)}><X className="mr-1 h-3 w-3" />取消</Button>
            </div>
          </div>
        )}

        {loading ? (
          <p className="text-sm text-muted-foreground">加载中...</p>
        ) : environments.length === 0 ? (
          <p className="text-sm text-muted-foreground">暂无测试环境</p>
        ) : (
          <div className="space-y-2">
            {environments.map((env) => (
              <div key={env.id} className="flex items-center justify-between rounded-lg border p-4">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-sm">{env.name}</span>
                    {env.is_default && (
                      <span className="rounded bg-blue-100 px-1.5 py-0.5 text-[10px] text-blue-700">默认</span>
                    )}
                  </div>
                  <p className="mt-0.5 text-xs text-muted-foreground">{env.base_url}</p>
                  {env.description && <p className="text-xs text-muted-foreground">{env.description}</p>}
                </div>
                <div className="flex gap-1">
                  <Button size="icon" variant="ghost" className="h-8 w-8" onClick={() => handleEdit(env)}>
                    <Pencil className="h-3.5 w-3.5" />
                  </Button>
                  <Button size="icon" variant="ghost" className="h-8 w-8 text-red-500" onClick={() => handleDelete(env.id)}>
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
