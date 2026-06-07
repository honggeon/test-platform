"use client";

import * as React from "react";
import {
  Upload,
  Download,
  FileSpreadsheet,
  Loader2,
  AlertCircle,
  Zap,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { toast } from "sonner";
import {
  importTestCases,
  importTestCasesFromApi,
  downloadTestCaseImportTemplate,
  type TestCaseImportResponse,
} from "@/lib/api/testCases";
import { listAPIEndpoints, type APIEndpoint } from "@/lib/api/api-endpoints";

interface ImportTestCasesDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  projectId: string;
  folderId?: string | null;
  folderName?: string;
  defaultEndpointId?: string | null;
  onSuccess?: (result: TestCaseImportResponse) => void;
}

const ACCEPTED_TYPES = ".csv,.xlsx,.xls,.json";

type ImportMode = "file" | "api";

function ImportResultPanel({ result }: { result: TestCaseImportResponse }) {
  if (result.errors.length === 0) return null;

  return (
    <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-3 max-h-40 overflow-y-auto">
      <div className="mb-2 flex items-center gap-2 text-sm font-medium text-destructive">
        <AlertCircle className="h-4 w-4" />
        失败 {result.failed_count} 条
      </div>
      <div className="space-y-1 text-xs text-muted-foreground">
        {result.errors.slice(0, 10).map((error, index) => (
          <p key={`${error.row}-${index}`}>
            {error.name ? `${error.name}：` : ""}
            {error.message}
          </p>
        ))}
        {result.errors.length > 10 && (
          <p>... 还有 {result.errors.length - 10} 条错误</p>
        )}
      </div>
    </div>
  );
}

export function ImportTestCasesDialog({
  open,
  onOpenChange,
  projectId,
  folderId,
  folderName,
  defaultEndpointId,
  onSuccess,
}: ImportTestCasesDialogProps) {
  const [mode, setMode] = React.useState<ImportMode>("file");
  const [file, setFile] = React.useState<File | null>(null);
  const [importing, setImporting] = React.useState(false);
  const [result, setResult] = React.useState<TestCaseImportResponse | null>(null);
  const fileInputRef = React.useRef<HTMLInputElement>(null);

  const [endpoints, setEndpoints] = React.useState<APIEndpoint[]>([]);
  const [loadingEndpoints, setLoadingEndpoints] = React.useState(false);
  const [selectedEndpointIds, setSelectedEndpointIds] = React.useState<Set<string>>(
    new Set()
  );

  React.useEffect(() => {
    if (!open) {
      setFile(null);
      setResult(null);
      setImporting(false);
      setMode(defaultEndpointId ? "api" : "file");
      setSelectedEndpointIds(defaultEndpointId ? new Set([defaultEndpointId]) : new Set());
      return;
    }

    const loadEndpoints = async () => {
      setLoadingEndpoints(true);
      try {
        const data = await listAPIEndpoints(projectId);
        setEndpoints(data || []);
        if (defaultEndpointId) {
          setSelectedEndpointIds(new Set([defaultEndpointId]));
          setMode("api");
        }
      } catch (error) {
        console.error("Failed to load API endpoints:", error);
        toast.error("加载 API 端点失败");
      } finally {
        setLoadingEndpoints(false);
      }
    };

    loadEndpoints();
  }, [open, projectId, defaultEndpointId]);

  const handleFileSelect = (selected: FileList | null) => {
    if (!selected || selected.length === 0) return;
    const nextFile = selected[0];
    const lowerName = nextFile.name.toLowerCase();
    if (
      !lowerName.endsWith(".csv") &&
      !lowerName.endsWith(".xlsx") &&
      !lowerName.endsWith(".xls") &&
      !lowerName.endsWith(".json")
    ) {
      toast.error("仅支持 CSV、Excel (.xlsx) 或 JSON 文件");
      return;
    }
    setFile(nextFile);
    setResult(null);
  };

  const handleImportFile = async () => {
    if (!file) {
      toast.error("请先选择文件");
      return;
    }

    setImporting(true);
    try {
      const response = await importTestCases(projectId, file, folderId);
      setResult(response);
      if (response.imported_count > 0) {
        toast.success(response.message);
        onSuccess?.(response);
      } else {
        toast.error(response.message);
      }
    } catch (error) {
      console.error("Import test cases failed:", error);
      toast.error(error instanceof Error ? error.message : "导入失败");
    } finally {
      setImporting(false);
    }
  };

  const handleImportFromApi = async () => {
    if (selectedEndpointIds.size === 0) {
      toast.error("请至少选择一个 API 端点");
      return;
    }

    setImporting(true);
    try {
      const response = await importTestCasesFromApi(
        projectId,
        Array.from(selectedEndpointIds),
        folderId
      );
      setResult(response);
      if (response.imported_count > 0) {
        toast.success(response.message);
        onSuccess?.(response);
      } else {
        toast.error(response.message);
      }
    } catch (error) {
      console.error("Import from API failed:", error);
      toast.error(error instanceof Error ? error.message : "导入失败");
    } finally {
      setImporting(false);
    }
  };

  const toggleEndpoint = (endpointId: string, checked: boolean) => {
    setSelectedEndpointIds((prev) => {
      const next = new Set(prev);
      if (checked) next.add(endpointId);
      else next.delete(endpointId);
      return next;
    });
  };

  const endpointsWithCases = endpoints.filter((ep) => ep.total_test_cases > 0);
  const targetLabel = folderName ? `文件夹「${folderName}」` : "项目根目录";
  const apiImportTargetLabel = folderName
    ? `将在「${folderName}」下按功能模块自动创建子文件夹`
    : "将按 Swagger 功能模块自动创建文件夹（如：项目管理 / 测试用例）";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>导入测试用例</DialogTitle>
          <DialogDescription>
            {mode === "api"
              ? `从 API 测试导入时，${apiImportTargetLabel}。`
              : `支持从文件导入到${targetLabel}，或从 API 测试导入并按功能模块自动归类。`}
          </DialogDescription>
        </DialogHeader>

        <div className="flex gap-2 border-b pb-3">
          <Button
            variant={mode === "file" ? "default" : "outline"}
            size="sm"
            onClick={() => setMode("file")}
          >
            <Upload className="mr-2 h-4 w-4" />
            文件导入
          </Button>
          <Button
            variant={mode === "api" ? "default" : "outline"}
            size="sm"
            onClick={() => setMode("api")}
          >
            <Zap className="mr-2 h-4 w-4" />
            从 API 测试导入
          </Button>
        </div>

        {mode === "file" ? (
          <div className="space-y-4 py-2">
            <div className="rounded-lg border border-dashed p-6 text-center">
              <input
                ref={fileInputRef}
                type="file"
                accept={ACCEPTED_TYPES}
                className="hidden"
                onChange={(e) => handleFileSelect(e.target.files)}
              />
              {file ? (
                <div className="flex flex-col items-center gap-2">
                  <FileSpreadsheet className="h-10 w-10 text-primary" />
                  <p className="text-sm font-medium">{file.name}</p>
                  <p className="text-xs text-muted-foreground">
                    {(file.size / 1024).toFixed(1)} KB
                  </p>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => fileInputRef.current?.click()}
                  >
                    重新选择
                  </Button>
                </div>
              ) : (
                <div className="flex flex-col items-center gap-3">
                  <Upload className="h-10 w-10 text-muted-foreground" />
                  <Button onClick={() => fileInputRef.current?.click()}>
                    选择文件
                  </Button>
                  <p className="text-xs text-muted-foreground">
                    支持 .csv / .xlsx / .json
                  </p>
                </div>
              )}
            </div>

            <div className="rounded-lg bg-muted/40 p-3 text-xs text-muted-foreground space-y-1">
              <p className="font-medium text-foreground">CSV/Excel 表头示例：</p>
              <p>name, description, preconditions, priority, status, case_type, tags, steps</p>
              <p>steps 格式：步骤1|预期1;;步骤2|预期2</p>
            </div>
          </div>
        ) : (
          <div className="space-y-3 py-2">
            <div className="rounded-lg bg-muted/40 p-3 text-xs text-muted-foreground space-y-1">
              <p>
                选择已在 <strong>API 测试</strong> 中生成过测试用例成果的接口，系统会把 MinIO 中的
                `test-cases.json` 转换为测试用例库记录。
              </p>
              <p>{apiImportTargetLabel}，同名文件夹会自动复用。</p>
            </div>

            {loadingEndpoints ? (
              <div className="flex items-center justify-center py-10 text-sm text-muted-foreground">
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                加载 API 端点...
              </div>
            ) : endpoints.length === 0 ? (
              <div className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
                当前项目还没有 API 端点，请先到 API 测试页导入接口并生成测试用例。
              </div>
            ) : (
              <ScrollArea className="h-64 rounded-lg border">
                <div className="divide-y">
                  {endpoints.map((endpoint) => {
                    const hasCases = endpoint.total_test_cases > 0;
                    return (
                      <label
                        key={endpoint.id}
                        className="flex cursor-pointer items-start gap-3 p-3 hover:bg-muted/40"
                      >
                        <Checkbox
                          checked={selectedEndpointIds.has(endpoint.id)}
                          onCheckedChange={(checked) =>
                            toggleEndpoint(endpoint.id, checked === true)
                          }
                          className="mt-1"
                        />
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2">
                            <Badge variant="outline">{endpoint.method}</Badge>
                            <span className="truncate text-sm font-medium">
                              {endpoint.display_name}
                            </span>
                          </div>
                          <p className="truncate text-xs text-muted-foreground">
                            {endpoint.path}
                          </p>
                        </div>
                        <Badge variant={hasCases ? "secondary" : "outline"}>
                          {hasCases ? `${endpoint.total_test_cases} 用例` : "无用例"}
                        </Badge>
                      </label>
                    );
                  })}
                </div>
              </ScrollArea>
            )}

            {endpointsWithCases.length === 0 && endpoints.length > 0 && (
              <p className="text-xs text-amber-600">
                暂无已生成测试用例的接口。请先在 API 测试页使用 AI 生成测试用例后再导入。
              </p>
            )}
          </div>
        )}

        {result && <ImportResultPanel result={result} />}

        <DialogFooter className="flex items-center justify-between sm:justify-between">
          {mode === "file" ? (
            <Button
              variant="outline"
              size="sm"
              onClick={() => downloadTestCaseImportTemplate(projectId)}
            >
              <Download className="mr-2 h-4 w-4" />
              下载模板
            </Button>
          ) : (
            <div className="text-xs text-muted-foreground">
              已选 {selectedEndpointIds.size} 个接口
            </div>
          )}
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => onOpenChange(false)}>
              取消
            </Button>
            <Button
              onClick={mode === "file" ? handleImportFile : handleImportFromApi}
              disabled={
                importing ||
                (mode === "file" ? !file : selectedEndpointIds.size === 0)
              }
            >
              {importing ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  导入中...
                </>
              ) : (
                "开始导入"
              )}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
