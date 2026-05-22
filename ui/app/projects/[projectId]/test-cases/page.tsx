"use client";

import * as React from "react";
import { useParams } from "next/navigation";
import { toast } from "sonner";
import { MainLayout } from "@/components/layout";
import { useLanguage } from "@/providers/LanguageProvider";
import { TestCaseList } from "@/components/test-cases";
import { TestCaseDialog } from "@/components/test-cases/test-case-dialog";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { AIChatContainer } from "@/components/langgraph/AIChatContainer";
import { ClientProvider } from "@/providers/ClientProvider";
import { getDeploymentUrl } from "@/lib/langgraph/config";
import { Assistant } from "@langchain/langgraph-sdk";
import { cn } from "@/lib/utils";
import {
  getFolderTestCases,
  createTestCase,
  updateTestCase,
  deleteTestCase,
  bulkDeleteTestCases,
} from "@/lib/api/testCases";
import type { TestCaseInfo, TestCaseCreate } from "@/lib/api/types";

export default function TestCasesPage() {
  const params = useParams();
  const projectId = params?.projectId as string;
  const { t } = useLanguage();

  const [testCases, setTestCases] = React.useState<TestCaseInfo[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [page, setPage] = React.useState(1);
  const [total, setTotal] = React.useState(0);
  const [searchQuery, setSearchQuery] = React.useState("");
  const [selectedIds, setSelectedIds] = React.useState<Set<string>>(new Set());
  const [editingTestCase, setEditingTestCase] = React.useState<TestCaseInfo | null>(null);
  const [testCaseDialogOpen, setTestCaseDialogOpen] = React.useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = React.useState(false);
  const [deletingTestCase, setDeletingTestCase] = React.useState<TestCaseInfo | null>(null);
  const [submitting, setSubmitting] = React.useState(false);
  const [assistant, setAssistant] = React.useState<Assistant | null>(null);
  const [aiChatOpen, setAiChatOpen] = React.useState(false);
  const pageSize = 20;

  const loadTestCases = React.useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, string | number | boolean | undefined> = { page, page_size: pageSize };
      if (searchQuery) params.search = searchQuery;
      const res = await getFolderTestCases(projectId, "", params);
      if (res.success) {
        setTestCases(res.data || res.test_cases || []);
        if (res.info) setTotal(res.info.total || 0);
      }
    } catch {
      toast.error("加载测试用例失败");
    }
    setLoading(false);
  }, [projectId, page, searchQuery]);

  React.useEffect(() => { loadTestCases(); }, [loadTestCases]);

  const handleSubmitTestCase = async (data: TestCaseCreate) => {
    setSubmitting(true);
    try {
      if (editingTestCase) {
        await updateTestCase(projectId, editingTestCase.id, data);
        toast.success("测试用例已更新");
      } else {
        await createTestCase(projectId, null, data);
        toast.success("测试用例已创建");
      }
      setTestCaseDialogOpen(false);
      await loadTestCases();
    } catch {
      toast.error("保存失败");
    }
    setSubmitting(false);
  };

  const handleDeleteTestCase = async () => {
    if (!deletingTestCase) return;
    setSubmitting(true);
    try {
      await deleteTestCase(projectId, deletingTestCase.id);
      toast.success("测试用例已删除");
      setDeleteDialogOpen(false);
      await loadTestCases();
    } catch {
      toast.error("删除失败");
    }
    setSubmitting(false);
  };

  const handleBulkDelete = async () => {
    try {
      await bulkDeleteTestCases(projectId, Array.from(selectedIds));
      toast.success("批量删除成功");
      setSelectedIds(new Set());
      await loadTestCases();
    } catch {
      toast.error("批量删除失败");
    }
  };

  React.useEffect(() => {
    getDeploymentUrl();
    const initAssistant = async () => {
      try {
        const { Client } = await import("@langchain/langgraph-sdk");
        const client = new Client({ apiUrl: getDeploymentUrl() });
        const assistants = await client.assistants.search();
        if (assistants.length > 0) setAssistant(assistants[0]);
      } catch {}
    };
    initAssistant();
  }, []);

  return (
    <MainLayout>
      <div className="relative flex h-full">
        <div className="flex-1 overflow-auto p-4">
          <TestCaseList
            testCases={testCases}
            loading={loading}
            selectedIds={selectedIds}
            onSelectIds={setSelectedIds}
            onSearch={(q) => { setSearchQuery(q); setPage(1); }}
            onCreateTestCase={() => { setEditingTestCase(null); setTestCaseDialogOpen(true); }}
            onEditTestCase={(tc) => { setEditingTestCase(tc); setTestCaseDialogOpen(true); }}
            onDeleteTestCase={(tc) => { setDeletingTestCase(tc); setDeleteDialogOpen(true); }}
            onBulkDelete={handleBulkDelete}
            onViewTestCase={(tc) => { setEditingTestCase(tc); setTestCaseDialogOpen(true); }}
            pagination={{
              page, pageSize, total,
              onPageChange: (p) => { setPage(p); setSelectedIds(new Set()); },
            }}
          />
        </div>

        {assistant && (
          <div className={cn(
            "absolute right-0 top-0 z-50 h-full w-[600px] bg-background transition-transform duration-300",
            aiChatOpen ? "translate-x-0 border-l shadow-2xl" : "translate-x-full"
          )}>
            <ClientProvider deploymentUrl={getDeploymentUrl()} apiKey="">
              <AIChatContainer
                assistant={assistant}
                onClose={() => setAiChatOpen(false)}
              />
            </ClientProvider>
          </div>
        )}
      </div>

      <TestCaseDialog
        open={testCaseDialogOpen}
        onOpenChange={setTestCaseDialogOpen}
        testCase={editingTestCase}
        onSubmit={handleSubmitTestCase}
        submitting={submitting}
        projectId={projectId}
      />

      <Dialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>确认删除</DialogTitle>
            <DialogDescription>
              确定要删除测试用例 &ldquo;{deletingTestCase?.name}&rdquo; 吗？
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteDialogOpen(false)}>取消</Button>
            <Button variant="destructive" onClick={handleDeleteTestCase} disabled={submitting}>
              {submitting ? "删除中..." : "删除"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </MainLayout>
  );
}
