"use client";

import * as React from "react";
import { useParams } from "next/navigation";
import { toast } from "sonner";
import { ClipboardList } from "lucide-react";
import { MainLayout } from "@/components/layout";
import { useLanguage } from "@/providers/LanguageProvider";
import { TestCaseList } from "@/components/test-cases";
import { FolderTree } from "@/components/test-cases/folder-tree";
import type { FolderTreeRef } from "@/components/test-cases/folder-tree";
import { TestCaseDialog } from "@/components/test-cases/test-case-dialog";
import { ImportTestCasesDialog } from "@/components/test-cases/import-test-cases-dialog";
import type { TestCaseFilters } from "@/components/test-cases/test-case-filter-panel";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  getTestCases,
  getFolderTestCases,
  createTestCase,
  updateTestCase,
  deleteTestCase,
  bulkDeleteTestCases,
} from "@/lib/api/testCases";
import {
  createFolder,
  updateFolder,
  deleteFolder,
} from "@/lib/api/folders";
import type {
  TestCaseInfo,
  TestCaseCreate,
  TestCaseTemplate,
  FolderInfo,
  FolderCreate,
} from "@/lib/api/types";

export default function TestCasesPage() {
  const params = useParams();
  const projectId = params?.projectId as string;
  const { t } = useLanguage();
  const folderTreeRef = React.useRef<FolderTreeRef>(null);

  const [testCases, setTestCases] = React.useState<TestCaseInfo[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [page, setPage] = React.useState(1);
  const [total, setTotal] = React.useState(0);
  const [filters, setFilters] = React.useState<TestCaseFilters>({ search: "" });
  const [selectedIds, setSelectedIds] = React.useState<Set<string>>(new Set());
  const [selectedFolderId, setSelectedFolderId] = React.useState<string | null>(null);
  const [selectedFolderName, setSelectedFolderName] = React.useState<string | undefined>();

  const [editingTestCase, setEditingTestCase] = React.useState<TestCaseInfo | null>(null);
  const [testCaseDialogOpen, setTestCaseDialogOpen] = React.useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = React.useState(false);
  const [deletingTestCase, setDeletingTestCase] = React.useState<TestCaseInfo | null>(null);
  const [submitting, setSubmitting] = React.useState(false);

  const [folderDialogOpen, setFolderDialogOpen] = React.useState(false);
  const [editingFolder, setEditingFolder] = React.useState<FolderInfo | null>(null);
  const [folderParentId, setFolderParentId] = React.useState<string | undefined>();
  const [folderFormData, setFolderFormData] = React.useState<FolderCreate>({
    name: "",
    description: "",
    folder_type: "test_case",
  });
  const [deleteFolderDialogOpen, setDeleteFolderDialogOpen] = React.useState(false);
  const [deletingFolder, setDeletingFolder] = React.useState<FolderInfo | null>(null);
  const [importDialogOpen, setImportDialogOpen] = React.useState(false);

  const pageSize = 20;

  const loadTestCases = React.useCallback(async () => {
    if (!projectId) return;

    setLoading(true);
    try {
      const queryParams: Record<string, string | number | boolean | undefined> = {
        p: page,
        page_size: pageSize,
      };
      if (filters.search) queryParams.search = filters.search;
      if (filters.status) queryParams.status = filters.status;
      if (filters.priority) queryParams.priority = filters.priority;

      const res = selectedFolderId
        ? await getFolderTestCases(projectId, selectedFolderId, queryParams)
        : await getTestCases(projectId, queryParams);

      if (res.success) {
        setTestCases(res.data || res.test_cases || []);
        setTotal(res.info?.total || 0);
      }
    } catch (error) {
      console.error("Failed to load test cases:", error);
      toast.error("加载测试用例失败");
    } finally {
      setLoading(false);
    }
  }, [projectId, page, pageSize, filters, selectedFolderId]);

  React.useEffect(() => {
    loadTestCases();
  }, [loadTestCases]);

  const handleSelectFolder = (folder: FolderInfo | null) => {
    setSelectedFolderId(folder?.id ?? null);
    setSelectedFolderName(folder?.name);
    setPage(1);
    setSelectedIds(new Set());
  };

  const handleSubmitTestCase = async (data: TestCaseCreate) => {
    setSubmitting(true);
    try {
      if (editingTestCase) {
        await updateTestCase(projectId, editingTestCase.id, data);
        toast.success("测试用例已更新");
      } else {
        await createTestCase(projectId, selectedFolderId, data);
        toast.success("测试用例已创建");
      }
      setTestCaseDialogOpen(false);
      setEditingTestCase(null);
      await loadTestCases();
      folderTreeRef.current?.refresh();
    } catch (error) {
      console.error("Failed to save test case:", error);
      toast.error("保存失败");
    } finally {
      setSubmitting(false);
    }
  };

  const handleQuickCreateTestCase = async (
    title: string,
    template: TestCaseTemplate
  ) => {
    try {
      await createTestCase(projectId, selectedFolderId, {
        name: title,
        template,
        priority: "medium",
        status: "new",
        case_type: "functional",
        test_case_steps: template === "test_case" ? [{ step: "", result: "" }] : undefined,
      });
      toast.success("测试用例已创建");
      await loadTestCases();
      folderTreeRef.current?.refresh();
    } catch (error) {
      console.error("Failed to quick create test case:", error);
      toast.error("创建失败");
    }
  };

  const handleDeleteTestCase = async () => {
    if (!deletingTestCase) return;
    setSubmitting(true);
    try {
      await deleteTestCase(projectId, deletingTestCase.id);
      toast.success("测试用例已删除");
      setDeleteDialogOpen(false);
      setDeletingTestCase(null);
      await loadTestCases();
      folderTreeRef.current?.refresh();
    } catch (error) {
      console.error("Failed to delete test case:", error);
      toast.error("删除失败");
    } finally {
      setSubmitting(false);
    }
  };

  const handleBulkDelete = async () => {
    try {
      await bulkDeleteTestCases(projectId, Array.from(selectedIds));
      toast.success("批量删除成功");
      setSelectedIds(new Set());
      await loadTestCases();
      folderTreeRef.current?.refresh();
    } catch (error) {
      console.error("Failed to bulk delete test cases:", error);
      toast.error("批量删除失败");
    }
  };

  const handleSubmitFolder = async () => {
    if (!folderFormData.name.trim()) {
      toast.error("请输入文件夹名称");
      return;
    }

    setSubmitting(true);
    try {
      if (editingFolder) {
        await updateFolder(projectId, editingFolder.id, {
          name: folderFormData.name,
          description: folderFormData.description,
        });
        folderTreeRef.current?.updateFolderLocally(editingFolder.id, {
          name: folderFormData.name,
          description: folderFormData.description,
        });
        toast.success("文件夹已更新");
      } else {
        const res = await createFolder(projectId, {
          ...folderFormData,
          folder_type: "test_case",
          parent_id: folderParentId,
        });
        if (res.success && res.data) {
          folderTreeRef.current?.addFolderLocally(res.data, folderParentId ?? null);
        }
        toast.success("文件夹已创建");
      }
      setFolderDialogOpen(false);
    } catch (error) {
      console.error("Failed to save folder:", error);
      toast.error("保存文件夹失败");
    } finally {
      setSubmitting(false);
    }
  };

  const handleDeleteFolder = async () => {
    if (!deletingFolder) return;

    try {
      await deleteFolder(projectId, deletingFolder.id);
      toast.success("文件夹已删除");
      setDeleteFolderDialogOpen(false);

      if (selectedFolderId === deletingFolder.id) {
        setSelectedFolderId(null);
        setSelectedFolderName(undefined);
      }

      folderTreeRef.current?.removeFolderLocally(deletingFolder.id);
      await loadTestCases();
    } catch (error) {
      console.error("Failed to delete folder:", error);
      toast.error("删除文件夹失败");
    }
  };

  return (
    <MainLayout title={t("testCases.title")}>
      <div className="flex h-[calc(100vh-8rem)] rounded-lg border bg-card overflow-hidden">
        <div className="w-72 shrink-0 border-r bg-muted/10">
          <FolderTree
            ref={folderTreeRef}
            projectId={projectId}
            folderType="test_case"
            selectedFolderId={selectedFolderId}
            onSelectFolder={handleSelectFolder}
            onCreateFolder={(parentId) => {
              setEditingFolder(null);
              setFolderParentId(parentId);
              setFolderFormData({ name: "", description: "", folder_type: "test_case" });
              setFolderDialogOpen(true);
            }}
            onEditFolder={(folder) => {
              setEditingFolder(folder);
              setFolderParentId(undefined);
              setFolderFormData({
                name: folder.name,
                description: folder.description || "",
                folder_type: "test_case",
              });
              setFolderDialogOpen(true);
            }}
            onDeleteFolder={(folder) => {
              setDeletingFolder(folder);
              setDeleteFolderDialogOpen(true);
            }}
            onCreateTestCase={(folder) => {
              setSelectedFolderId(folder.id);
              setSelectedFolderName(folder.name);
              setEditingTestCase(null);
              setTestCaseDialogOpen(true);
            }}
          />
        </div>

        <div className="flex-1 min-w-0">
          <TestCaseList
            projectId={projectId}
            testCases={testCases}
            loading={loading}
            selectedIds={selectedIds}
            onSelectIds={setSelectedIds}
            onSearch={(q) => {
              setFilters((prev) => ({ ...prev, search: q }));
              setPage(1);
            }}
            onFilterChange={(nextFilters) => {
              setFilters(nextFilters);
              setPage(1);
            }}
            onCreateTestCase={() => {
              setEditingTestCase(null);
              setTestCaseDialogOpen(true);
            }}
            onEditTestCase={(tc) => {
              setEditingTestCase(tc);
              setTestCaseDialogOpen(true);
            }}
            onDeleteTestCase={(tc) => {
              setDeletingTestCase(tc);
              setDeleteDialogOpen(true);
            }}
            onBulkDelete={handleBulkDelete}
            onViewTestCase={(tc) => {
              setEditingTestCase(tc);
              setTestCaseDialogOpen(true);
            }}
            onLatestResultChange={(updated) => {
              setTestCases((prev) =>
                prev.map((tc) => (tc.id === updated.id ? updated : tc))
              );
            }}
            onQuickCreateTestCase={handleQuickCreateTestCase}
            onImport={() => setImportDialogOpen(true)}
            folderName={selectedFolderName || "全部用例"}
            pagination={{
              page,
              pageSize,
              total,
              onPageChange: (p) => {
                setPage(p);
                setSelectedIds(new Set());
              },
            }}
          />
        </div>
      </div>

      <TestCaseDialog
        open={testCaseDialogOpen}
        onOpenChange={setTestCaseDialogOpen}
        testCase={editingTestCase}
        onSubmit={handleSubmitTestCase}
        submitting={submitting}
        projectId={projectId}
        folderName={selectedFolderName}
      />

      <ImportTestCasesDialog
        open={importDialogOpen}
        onOpenChange={setImportDialogOpen}
        projectId={projectId}
        folderId={selectedFolderId}
        folderName={selectedFolderName}
        onSuccess={async () => {
          await loadTestCases();
          folderTreeRef.current?.refresh();
        }}
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
            <Button variant="outline" onClick={() => setDeleteDialogOpen(false)}>
              取消
            </Button>
            <Button
              variant="destructive"
              onClick={handleDeleteTestCase}
              disabled={submitting}
            >
              {submitting ? "删除中..." : "删除"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={folderDialogOpen} onOpenChange={setFolderDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{editingFolder ? "编辑文件夹" : "创建文件夹"}</DialogTitle>
            <DialogDescription>
              {editingFolder ? "修改文件夹信息" : "在当前项目下创建新的测试用例文件夹"}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="folder-name">文件夹名称</Label>
              <Input
                id="folder-name"
                value={folderFormData.name}
                onChange={(e) =>
                  setFolderFormData({ ...folderFormData, name: e.target.value })
                }
                placeholder="输入文件夹名称"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="folder-description">描述</Label>
              <Textarea
                id="folder-description"
                value={folderFormData.description}
                onChange={(e) =>
                  setFolderFormData({
                    ...folderFormData,
                    description: e.target.value,
                  })
                }
                placeholder="可选描述"
                rows={3}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setFolderDialogOpen(false)}>
              取消
            </Button>
            <Button onClick={handleSubmitFolder} disabled={submitting}>
              {submitting ? "保存中..." : editingFolder ? "保存" : "创建"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={deleteFolderDialogOpen} onOpenChange={setDeleteFolderDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>确认删除文件夹</DialogTitle>
            <DialogDescription>
              确定要删除文件夹 &ldquo;{deletingFolder?.name}&rdquo; 吗？文件夹内的测试用例可能受影响。
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteFolderDialogOpen(false)}>
              取消
            </Button>
            <Button variant="destructive" onClick={handleDeleteFolder}>
              删除
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </MainLayout>
  );
}
