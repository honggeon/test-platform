/**
 * 版权所有 (c) 2023-2026 北京慧测信息技术有限公司(但问智能) 保留所有权利。
 * 
 * 本代码版权归北京慧测信息技术有限公司(但问智能)所有，仅用于学习交流目的，未经公司商业授权，
 * 不得用于任何商业用途，包括但不限于商业环境部署、售卖或以任何形式进行商业获利。违者必究。
 * 
 * 授权商业应用请联系微信：huice666
 */

/**
 * API 测试生成对话框
 */
"use client";

import * as React from "react";
import { useState } from "react";
import { Sparkles, Loader2, Link as LinkIcon, Upload, FileCode, ChevronLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";
import { uploadSchema, generateFromSchema } from "@/lib/api/api-tests";
import { useLanguage } from "@/providers/LanguageProvider";

type SchemaSource = "url" | "file";

interface AIGenerateAPITestDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  projectIdentifier: string;
  onSuccess?: () => void;
  onOpenChat?: (prompt: string) => void;
}

export function AIGenerateAPITestDialog({
  open,
  onOpenChange,
  projectIdentifier,
  onSuccess,
  onOpenChat,
}: AIGenerateAPITestDialogProps) {
  const [currentStep, setCurrentStep] = useState<"input" | "uploading" | "generating">("input");
  const [schemaSource, setSchemaSource] = useState<SchemaSource>("url");
  const [schemaUrl, setSchemaUrl] = useState("");
  const [schemaFile, setSchemaFile] = useState<File | null>(null);
  const [prompt, setPrompt] = useState(""); // 新增：用户输入的功能描述
  const [scriptFormat, setScriptFormat] = useState("hat");
  const [scriptLanguage, setScriptLanguage] = useState("yaml");
  const [uploading, setUploading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [schemaPath, setSchemaPath] = useState("");

  // 重置表单
  const resetForm = () => {
    setCurrentStep("input");
    setSchemaSource("url");
    setSchemaUrl("");
    setSchemaFile(null);
    setPrompt(""); // 重置提示词
    setScriptFormat("hat");
    setScriptLanguage("yaml");
    setUploading(false);
    setGenerating(false);
    setSchemaPath("");
  };

  const handleOpenChange = (open: boolean) => {
    if (!open) {
      resetForm();
    }
    onOpenChange(open);
  };

  // 处理 Schema 上传
  const handleSchemaUpload = async () => {
    if (schemaSource === "url" && !schemaUrl.trim()) {
      toast.error("请输入 Schema URL");
      return;
    }
    if (schemaSource === "file" && !schemaFile) {
      toast.error("请选择 Schema 文件");
      return;
    }

    // 如果提供了 onOpenChat 回调，使用聊天界面
    if (onOpenChat) {
      const chatPrompt = `请为当前项目生成 API 测试。

📋 工作流程：
1. **获取端点信息** → 使用 \`get_endpoint_details\` 或 \`list_api_endpoints\` 工具获取已解析的 API 端点信息（端点数据已在平台数据库中，无需自行抓取 schema）
2. **生成测试计划** → 参考 hat-test-planner（含「生成指引」认证配置），\`save_test_plan\` 保存
3. **生成 HAT 脚本** → hat-test-generator：\`基础配置\`+\`用例步骤\`，文件 \`0_*.yaml\`；Bearer 须 \`0_login.yaml\` 或 context \`{{AUTH_TOKEN}}\`；\`deploy_hat_case\` 部署
4. **保存元数据** → \`save_test_script(script_format="hat")\`
5. **执行测试** → \`execute_api_script(framework="hat")\` 指向 deploy 返回的用例目录

⚠️ 重要提醒：
- 端点信息已经通过平台 API 解析完成，**不要**自行运行任何命令去获取 schema
- 直接使用平台提供的 \`get_endpoint_details\` / \`list_api_endpoints\` 工具获取端点数据
- 严格按照工具职责执行，不得混淆使用

${prompt.trim() ? `📝 特殊要求：${prompt.trim()}` : ""}`;

      onOpenChat(chatPrompt);
      resetForm();
      return;
    }

    // 否则使用原来的 API 方式
    setUploading(true);
    try {
      let uploadResult;

      if (schemaSource === "file" && schemaFile) {
        uploadResult = await uploadSchema(projectIdentifier, schemaFile);
      } else {
        uploadResult = {
          schema_path: "",
          schema_url: schemaUrl,
        };
      }

      setSchemaPath(uploadResult.schema_path);

      // 进入生成步骤
      setCurrentStep("generating");
      await handleGenerate(uploadResult);

    } catch (error: any) {
      console.error("上传 Schema 失败:", error);
      toast.error(error.message || "上传 Schema 失败");
    } finally {
      setUploading(false);
    }
  };

  // 调用 AI 生成
  const handleGenerate = async (uploadResult: any) => {
    setGenerating(true);

    try {
      const result = await generateFromSchema(projectIdentifier, {
        schema_url: schemaSource === "url" ? schemaUrl : undefined,
        schema_path: schemaSource === "file" ? uploadResult.schema_path : undefined,
        script_format: scriptFormat,
        script_language: scriptLanguage,
        include_auth: true,
        include_security: false,
        include_error_handling: true,
      });

      toast.success(`成功生成 ${result.statistics.total_scenarios} 个测试场景`);

      // 关闭对话框
      resetForm();
      onOpenChange(false);
      onSuccess?.();

    } catch (error: any) {
      console.error("AI 生成失败:", error);
      toast.error(error.message || "AI 生成失败，请稍后重试");
      setCurrentStep("input");
    } finally {
      setGenerating(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-xl">
            <Sparkles className="h-5 w-5 text-primary" />
            AI 生成 API 测试
          </DialogTitle>
          <DialogDescription className="text-base">
            上传 OpenAPI/Swagger Schema，AI 将自动生成完整的 API 测试脚本
          </DialogDescription>

          {/* 安全提示 */}
          <div className="flex items-center gap-2 rounded-lg bg-green-50 px-3 py-2 text-sm text-green-700 mt-3">
            <svg className="h-4 w-4 shrink-0" viewBox="0 0 20 20" fill="currentColor">
              <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
            </svg>
            <span>您的数据是安全的，不会用于 AI 训练</span>
          </div>
        </DialogHeader>

        {currentStep === "input" && (
          <div className="space-y-6 py-4">
            {/* 功能描述 - 新增 */}
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <Label className="text-sm font-medium">功能描述（可选）</Label>
              </div>

              {/* 快捷建议 */}
              <div className="flex flex-wrap gap-2">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="h-auto py-2 px-3 text-xs"
                  onClick={() => setPrompt("需要生成包含认证、参数验证、错误处理的完整测试用例")}
                >
                  <Sparkles className="h-3 w-3 mr-1" />
                  完整测试（含认证和错误处理）
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="h-auto py-2 px-3 text-xs"
                  onClick={() => setPrompt("重点关注边界条件和异常场景的测试")}
                >
                  <Sparkles className="h-3 w-3 mr-1" />
                  边界和异常测试
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="h-auto py-2 px-3 text-xs"
                  onClick={() => setPrompt("需要包含性能测试和压力测试的场景")}
                >
                  <Sparkles className="h-3 w-3 mr-1" />
                  性能和压力测试
                </Button>
              </div>

              {/* 描述输入框 */}
              <Textarea
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                placeholder="例如：需要特别测试用户认证、权限验证、数据校验等场景..."
                rows={4}
                className="resize-none"
              />
              <p className="text-xs text-muted-foreground flex items-start gap-1">
                <span className="text-primary">💡</span>
                <span>可选。描述您希望测试的特定场景、关注点或特殊要求，AI 会根据您的需求生成更精准的测试脚本。</span>
              </p>
            </div>

            {/* Schema 来源选择 */}
            <div className="space-y-3">
              <Label>Schema 来源</Label>
              <div className="flex gap-3">
                <Button
                  type="button"
                  variant={schemaSource === "url" ? "default" : "outline"}
                  onClick={() => setSchemaSource("url")}
                  className="flex-1"
                >
                  <LinkIcon className="mr-2 h-4 w-4" />
                  URL 链接
                </Button>
                <Button
                  type="button"
                  variant={schemaSource === "file" ? "default" : "outline"}
                  onClick={() => setSchemaSource("file")}
                  className="flex-1"
                >
                  <Upload className="mr-2 h-4 w-4" />
                  上传文件
                </Button>
              </div>
            </div>

            {/* URL 输入 */}
            {schemaSource === "url" && (
              <div className="space-y-2">
                <Label htmlFor="schemaUrl">
                  OpenAPI/Swagger URL <span className="text-destructive">*</span>
                </Label>
                <Input
                  id="schemaUrl"
                  value={schemaUrl}
                  onChange={(e) => setSchemaUrl(e.target.value)}
                  placeholder="https://api.example.com/openapi.json"
                />
                <p className="text-xs text-muted-foreground">
                  支持公开的 OpenAPI/Swagger JSON 或 YAML URL
                </p>
              </div>
            )}

            {/* 文件上传 */}
            {schemaSource === "file" && (
              <div className="space-y-2">
                <Label>
                  Schema 文件 <span className="text-destructive">*</span>
                </Label>
                <div className="border-2 border-dashed rounded-lg p-8 text-center">
                  <input
                    type="file"
                    id="schemaFile"
                    accept=".json,.yaml,.yml"
                    className="hidden"
                    onChange={(e) => {
                      const file = e.target.files?.[0];
                      if (file) {
                        setSchemaFile(file);
                      }
                    }}
                  />
                  <label htmlFor="schemaFile" className="cursor-pointer">
                    <div className="flex flex-col items-center gap-3">
                      <FileCode className="h-10 w-10 text-muted-foreground" />
                      <div>
                        <p className="text-sm font-medium">
                          {schemaFile?.name || "点击选择文件"}
                        </p>
                        <p className="text-xs text-muted-foreground mt-1">
                          支持 JSON, YAML 格式，最大 10MB
                        </p>
                      </div>
                    </div>
                  </label>
                </div>
              </div>
            )}

            {/* 脚本格式 */}
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>脚本格式</Label>
                <Select value={scriptFormat} onValueChange={setScriptFormat}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="hat">HAT</SelectItem>
                    <SelectItem value="playwright">Playwright</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>脚本语言</Label>
                <Select value={scriptLanguage} onValueChange={setScriptLanguage}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="yaml">YAML</SelectItem>
                    <SelectItem value="typescript">TypeScript</SelectItem>
                    <SelectItem value="javascript">JavaScript</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
          </div>
        )}

        {currentStep === "uploading" && (
          <div className="flex flex-col items-center justify-center py-16 space-y-6">
            <div className="relative">
              <div className="absolute inset-0 bg-primary/20 rounded-full animate-ping" />
              <Loader2 className="relative h-16 w-16 animate-spin text-primary" />
            </div>
            <div className="text-center space-y-2">
              <h3 className="text-lg font-semibold">上传 Schema 中...</h3>
              <p className="text-sm text-muted-foreground">
                正在上传到文件存储
              </p>
            </div>
          </div>
        )}

        {currentStep === "generating" && (
          <div className="flex flex-col items-center justify-center py-16 space-y-6">
            <div className="relative">
              <div className="absolute inset-0 bg-primary/20 rounded-full animate-ping" />
              <Loader2 className="relative h-16 w-16 animate-spin text-primary" />
            </div>
            <div className="text-center space-y-2">
              <h3 className="text-lg font-semibold">AI 正在生成测试脚本...</h3>
              <p className="text-sm text-muted-foreground">
                分析 API Schema，生成测试场景和断言...
              </p>
            </div>
          </div>
        )}

        <DialogFooter className="gap-2">
          {currentStep === "input" && (
            <>
              <Button
                variant="outline"
                onClick={() => onOpenChange(false)}
                disabled={uploading || generating}
              >
                取消
              </Button>
              <Button
                onClick={handleSchemaUpload}
                disabled={uploading || generating}
              >
                {uploading ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    处理中...
                  </>
                ) : (
                  <>
                    <Sparkles className="mr-2 h-4 w-4" />
                    生成测试
                  </>
                )}
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
