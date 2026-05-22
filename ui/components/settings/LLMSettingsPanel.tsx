"use client";

import * as React from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card } from "@/components/ui/card";
import {
  Settings,
  Eye,
  EyeOff,
  Loader2,
  Check,
  AlertCircle,
  Brain,
} from "lucide-react";
import {
  type LLMProvider,
  type LLMConfigData,
  type LLMConfigResponse,
  PROVIDER_META,
  getLLMConfig,
  saveLLMConfig,
} from "@/lib/api/llm-config";

interface LLMSettingsPanelProps {
  projectId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function LLMSettingsPanel({
  projectId,
  open,
  onOpenChange,
}: LLMSettingsPanelProps) {
  const [provider, setProvider] = React.useState<LLMProvider>("deepseek");
  const [modelName, setModelName] = React.useState("");
  const [apiKey, setApiKey] = React.useState("");
  const [showApiKey, setShowApiKey] = React.useState(false);
  const [baseUrl, setBaseUrl] = React.useState("");
  const [temperature, setTemperature] = React.useState<number | null>(0.7);
  const [maxTokens, setMaxTokens] = React.useState<number | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [saving, setSaving] = React.useState(false);
  const [saveStatus, setSaveStatus] = React.useState<
    "idle" | "success" | "error"
  >("idle");
  const [error, setError] = React.useState("");

  // 加载已有配置
  React.useEffect(() => {
    if (!open || !projectId) return;

    const load = async () => {
      setLoading(true);
      setError("");
      try {
        const res = await getLLMConfig(projectId);
        if (res.success && res.data) {
          const cfg = res.data;
          setProvider(cfg.provider as LLMProvider);
          setModelName(cfg.model_name || "");
          setApiKey(cfg.api_key || "");
          setBaseUrl(cfg.base_url || "");
          setTemperature(cfg.temperature);
          setMaxTokens(cfg.max_tokens);
        }
      } catch (e: unknown) {
        // 没有配置是正常的，使用默认值
        setProvider("deepseek");
        setModelName("");
        setApiKey("");
        setBaseUrl("");
        setTemperature(0.7);
        setMaxTokens(null);
      } finally {
        setLoading(false);
      }
    };

    load();
  }, [open, projectId]);

  // 当切换 Provider 时，如果 modelName 为空，填入默认值
  const handleProviderChange = (p: LLMProvider) => {
    setProvider(p);
    if (!modelName.trim()) {
      setModelName(PROVIDER_META[p].defaultModel);
    }
    setSaveStatus("idle");
  };

  const handleSave = async () => {
    setSaving(true);
    setSaveStatus("idle");
    setError("");
    try {
      const meta = PROVIDER_META[provider];
      const data: LLMConfigData = {
        provider,
        model_name: modelName.trim() || meta.defaultModel,
        api_key: meta.needApiKey ? apiKey.trim() || null : null,
        base_url: meta.needBaseUrl ? baseUrl.trim() || null : null,
        temperature,
        max_tokens: maxTokens,
      };
      await saveLLMConfig(projectId, data);
      setSaveStatus("success");
      setTimeout(() => setSaveStatus("idle"), 2000);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "保存失败");
      setSaveStatus("error");
    } finally {
      setSaving(false);
    }
  };

  const meta = PROVIDER_META[provider];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Brain className="h-5 w-5 text-primary" />
            AI 模型设置
          </DialogTitle>
          <DialogDescription>
            为当前项目配置 LLM Provider 和模型参数
          </DialogDescription>
        </DialogHeader>

        {loading ? (
          <div className="flex items-center justify-center gap-2 py-8 text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            <span className="text-sm">加载配置中...</span>
          </div>
        ) : (
          <div className="space-y-5">
            {/* Provider 选择 */}
            <div className="space-y-2">
              <Label>模型提供商</Label>
              <div className="grid grid-cols-2 gap-2">
                {(Object.keys(PROVIDER_META) as LLMProvider[]).map((p) => (
                  <Card
                    key={p}
                    onClick={() => handleProviderChange(p)}
                    className={`cursor-pointer p-3 transition-all border-2 ${
                      provider === p
                        ? "border-primary bg-primary/5"
                        : "border-transparent hover:border-border"
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <span className="text-lg">{PROVIDER_META[p].icon}</span>
                      <span className="text-sm font-medium">
                        {PROVIDER_META[p].label}
                      </span>
                    </div>
                  </Card>
                ))}
              </div>
            </div>

            {/* 模型名称 */}
            <div className="space-y-2">
              <Label htmlFor="model-name">模型名称</Label>
              <Input
                id="model-name"
                value={modelName}
                onChange={(e) => {
                  setModelName(e.target.value);
                  setSaveStatus("idle");
                }}
                placeholder={meta.placeholder}
                className="font-mono text-sm"
              />
              <p className="text-xs text-muted-foreground">
                默认: {meta.defaultModel}
              </p>
            </div>

            {/* API Key */}
            {meta.needApiKey && (
              <div className="space-y-2">
                <Label htmlFor="api-key">API Key</Label>
                <div className="relative">
                  <Input
                    id="api-key"
                    type={showApiKey ? "text" : "password"}
                    value={apiKey}
                    onChange={(e) => {
                      setApiKey(e.target.value);
                      setSaveStatus("idle");
                    }}
                    placeholder={`输入 ${meta.label} API Key`}
                    className="pr-10 font-mono text-sm"
                  />
                  <button
                    type="button"
                    onClick={() => setShowApiKey(!showApiKey)}
                    className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-muted-foreground hover:text-foreground transition-colors"
                    tabIndex={-1}
                  >
                    {showApiKey ? (
                      <EyeOff className="h-4 w-4" />
                    ) : (
                      <Eye className="h-4 w-4" />
                    )}
                  </button>
                </div>
              </div>
            )}

            {/* Base URL */}
            {meta.needBaseUrl && (
              <div className="space-y-2">
                <Label htmlFor="base-url">
                  Base URL{" "}
                  <span className="text-muted-foreground font-normal">
                    (可选)
                  </span>
                </Label>
                <Input
                  id="base-url"
                  value={baseUrl}
                  onChange={(e) => {
                    setBaseUrl(e.target.value);
                    setSaveStatus("idle");
                  }}
                  placeholder={meta.baseUrlPlaceholder}
                  className="font-mono text-sm"
                />
                {meta.baseUrlHelper && (
                  <p className="text-xs text-muted-foreground">
                    {meta.baseUrlHelper}
                  </p>
                )}
              </div>
            )}

            {/* 温度参数 */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label htmlFor="temperature">温度参数 (Temperature)</Label>
                <span className="text-xs font-mono text-muted-foreground bg-muted px-2 py-0.5 rounded">
                  {temperature ?? "默认"}
                </span>
              </div>
              <input
                id="temperature"
                type="range"
                min={0}
                max={2}
                step={0.1}
                value={temperature ?? 0.7}
                onChange={(e) => {
                  setTemperature(parseFloat(e.target.value));
                  setSaveStatus("idle");
                }}
                className="w-full h-2 bg-muted rounded-lg appearance-none cursor-pointer accent-primary"
              />
              <div className="flex justify-between text-[10px] text-muted-foreground">
                <span>精确 (0)</span>
                <span>平衡 (1)</span>
                <span>创意 (2)</span>
              </div>
            </div>

            {/* 最大 Token */}
            <div className="space-y-2">
              <Label htmlFor="max-tokens">
                最大 Token 数{" "}
                <span className="text-muted-foreground font-normal">
                  (可选)
                </span>
              </Label>
              <Input
                id="max-tokens"
                type="number"
                value={maxTokens ?? ""}
                onChange={(e) => {
                  const val = e.target.value;
                  setMaxTokens(val ? parseInt(val) : null);
                  setSaveStatus("idle");
                }}
                placeholder="不限制"
                className="font-mono text-sm"
              />
            </div>

            {/* 隐私提示 */}
            <div className="rounded-lg border bg-muted/50 p-3">
              <div className="flex gap-2 items-start">
                <Settings className="h-4 w-4 text-muted-foreground mt-0.5 shrink-0" />
                <p className="text-xs text-muted-foreground leading-relaxed">
                  API Key 保存在后端数据库中，不会发送到前端。Agent
                  运行时在后端直接调用 LLM Provider。
                </p>
              </div>
            </div>

            {/* 错误提示 */}
            {error && (
              <div className="flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 p-3 text-red-600 text-sm">
                <AlertCircle className="h-4 w-4 shrink-0" />
                {error}
              </div>
            )}
          </div>
        )}

        <DialogFooter className="gap-2">
          <div className="flex items-center gap-2 mr-auto">
            {saveStatus === "success" && (
              <span className="flex items-center gap-1 text-sm text-green-600 animate-in fade-in">
                <Check className="h-4 w-4" />
                已保存
              </span>
            )}
          </div>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button onClick={handleSave} disabled={saving || loading}>
            {saving ? (
              <>
                <Loader2 className="mr-1 h-4 w-4 animate-spin" />
                保存中
              </>
            ) : (
              "保存"
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
