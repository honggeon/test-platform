/**
 * 社区筛选与着色组件
 *
 * 为图谱节点按社区分组着色，提供社区筛选功能。
 */

"use client";

import * as React from "react";

export interface CommunityInfo {
  id: string;
  name: string;
  label: string;
  symbol_count: number;
  color: string;
}

interface CommunityFilterProps {
  communities: CommunityInfo[];
  selected: string | null;
  onSelect: (id: string | null) => void;
}

export function CommunityFilter({ communities, selected, onSelect }: CommunityFilterProps) {
  if (communities.length === 0) return null;

  return (
    <div className="flex flex-wrap gap-1.5">
      <button
        onClick={() => onSelect(null)}
        className={`px-2 py-0.5 text-[10px] rounded-full border transition-colors ${
          selected === null
            ? "bg-primary text-primary-foreground border-primary"
            : "border-border hover:bg-muted bg-white"
        }`}
      >
        全部社区
      </button>
      {communities.map((c) => (
        <button
          key={c.id}
          onClick={() => onSelect(c.id === selected ? null : c.id)}
          className={`flex items-center gap-1 px-2 py-0.5 text-[10px] rounded-full border transition-colors ${
            c.id === selected
              ? "ring-1 ring-primary"
              : ""
          }`}
          style={{
            backgroundColor: c.id === selected ? c.color : "white",
            color: c.id === selected ? "white" : c.color,
            borderColor: c.color,
          }}
          title={c.label}
        >
          <span
            className="h-1.5 w-1.5 rounded-full"
            style={{ backgroundColor: c.id === selected ? "white" : c.color }}
          />
          {c.label} ({c.symbol_count})
        </button>
      ))}
    </div>
  );
}
