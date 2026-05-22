/**
 * 版权所有 (c) 2023-2026 北京慧测信息技术有限公司(但问智能) 保留所有权利。
 * 
 * 本代码版权归北京慧测信息技术有限公司(但问智能)所有，仅用于学习交流目的，未经公司商业授权，
 * 不得用于任何商业用途，包括但不限于商业环境部署、售卖或以任何形式进行商业获利。违者必究。
 * 
 * 授权商业应用请联系微信：huice666
 */

/**
 * Monaco Code Editor 组件
 *
 * 使用 Monaco Editor (VS Code 的编辑器核心) 提供专业的代码编辑体验
 */

"use client";

import React, { useRef, useEffect } from "react";
import Editor, { OnMount, OnChange } from "@monaco-editor/react";
import * as monaco from "monaco-editor";

interface CodeEditorProps {
  value: string;
  onChange: (value: string) => void;
  language: string;
  readOnly?: boolean;
  height?: string;
  minimap?: boolean;
  fontSize?: number;
  onSave?: () => void;
}

export function MonacoCodeEditor({
  value,
  onChange,
  language,
  readOnly = false,
  height = "500px",
  minimap = false,
  fontSize = 14,
  onSave,
}: CodeEditorProps) {
  const editorRef = useRef<any>(null);

  const handleEditorDidMount: OnMount = (editor, monaco) => {
    editorRef.current = editor;

    // 添加保存快捷键 (Ctrl+S / Cmd+S)
    editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () => {
      if (onSave) {
        onSave();
      }
      return null;
    });

    // 确保编辑器在挂载后立即布局
    setTimeout(() => {
      editor.layout();
    }, 100);
  };

  const handleChange: OnChange = (value) => {
    onChange(value || "");
  };

  return (
    <div className="border-0 rounded-lg overflow-hidden shadow-sm h-full">
      <Editor
        height={height}
        language={language}
        value={value}
        onChange={handleChange}
        onMount={handleEditorDidMount}
        theme="vs"
        options={{
          readOnly,
          minimap: { enabled: minimap },
          fontSize,
          lineHeight: 20,
          fontFamily: "'JetBrains Mono', 'Fira Code', 'Consolas', monospace",
          fontLigatures: true,
          tabSize: 2,
          scrollBeyondLastLine: false,
          automaticLayout: true,
          wordWrap: "on",
          formatOnPaste: true,
          formatOnType: true,
        }}
      />
    </div>
  );
}
