/**
 * 版权所有 (c) 2023-2026 北京慧测信息技术有限公司(但问智能) 保留所有权利。
 * 
 * 本代码版权归北京慧测信息技术有限公司(但问智能)所有，仅用于学习交流目的，未经公司商业授权，
 * 不得用于任何商业用途，包括但不限于商业环境部署、售卖或以任何形式进行商业获利。违者必究。
 * 
 * 授权商业应用请联系微信：huice666
 */

/**
 * 代码查看器组件
 * 支持语法高亮和行号显示
 */
"use client";

import { useState } from "react";
import { Copy, Check, Edit3, Eye } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";

interface CodeViewerProps {
  code: string;
  language?: string;
  readOnly?: boolean;
  onChange?: (code: string) => void;
  onCopy?: () => void;
}

export function CodeViewer({
  code,
  language = "typescript",
  readOnly = false,
  onChange,
  onCopy,
}: CodeViewerProps) {
  const [editing, setEditing] = useState(!readOnly);
  const [copied, setCopied] = useState(false);

  // 复制代码
  const handleCopy = () => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    toast.success("已复制到剪贴板");
    onCopy?.();
    setTimeout(() => setCopied(false), 2000);
  };

  // 切换编辑/查看模式
  const toggleEditMode = () => {
    if (readOnly) return;
    setEditing(!editing);
  };

  // 计算行数
  const lines = code.split("\n");

  return (
    <div className="relative h-full flex flex-col bg-muted/30 rounded-lg border">
      {/* 工具栏 */}
      <div className="flex items-center justify-between px-4 py-2 border-b bg-muted/50">
        <div className="flex items-center gap-2">
          <Badge variant="outline" className="text-xs">
            {language}
          </Badge>
          <span className="text-xs text-muted-foreground">
            {lines.length} 行
          </span>
        </div>
        <div className="flex items-center gap-2">
          {!readOnly && (
            <Button
              variant="ghost"
              size="sm"
              onClick={toggleEditMode}
              className="h-7"
            >
              {editing ? (
                <>
                  <Eye className="mr-1 h-3 w-3" />
                  查看
                </>
              ) : (
                <>
                  <Edit3 className="mr-1 h-3 w-3" />
                  编辑
                </>
              )}
            </Button>
          )}
          <Button
            variant="ghost"
            size="sm"
            onClick={handleCopy}
            className="h-7"
          >
            {copied ? (
              <>
                <Check className="mr-1 h-3 w-3" />
                已复制
              </>
            ) : (
              <>
                <Copy className="mr-1 h-3 w-3" />
                复制
              </>
            )}
          </Button>
        </div>
      </div>

      {/* 代码编辑器/查看器 */}
      <div className="flex-1 flex overflow-hidden">
        {/* 行号 */}
        <div className="py-4 px-2 bg-muted/50 text-right text-sm text-muted-foreground select-none border-r">
          {lines.map((_, index) => (
            <div key={index} className="leading-6">
              {index + 1}
            </div>
          ))}
        </div>

        {/* 代码内容 */}
        <div className="flex-1 overflow-auto">
          {editing ? (
            <textarea
              value={code}
              onChange={(e) => onChange?.(e.target.value)}
              className="w-full h-full p-4 bg-transparent font-mono text-sm resize-none focus:outline-none leading-6"
              spellCheck={false}
              style={{ tabSize: 2 }}
            />
          ) : (
            <pre className="p-4 font-mono text-sm leading-6">
              <code>{code}</code>
            </pre>
          )}
        </div>
      </div>
    </div>
  );
}
