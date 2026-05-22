"use client";

import * as React from "react";
import { Network, Expand, Minimize2 } from "lucide-react";
import { CyberGraph3D, type GraphNodeData, type GraphEdgeData } from "@/components/kg/CyberGraph3D";
import { CommunityFilter, type CommunityInfo } from "@/components/kg/CommunityFilter";

interface GraphExplorerProps {
  nodes: GraphNodeData[];
  edges: GraphEdgeData[];
  width: number;
  height: number;
  communities: CommunityInfo[];
  onNodeClick?: (nodeId: string) => void;
  onClose: () => void;
}

export function GraphExplorer({
  nodes,
  edges,
  width,
  height,
  communities,
  onNodeClick,
  onClose,
}: GraphExplorerProps) {
  const [visibleNodeTypes, setVisibleNodeTypes] = React.useState<string[]>([]);
  const [visibleEdgeTypes, setVisibleEdgeTypes] = React.useState<string[]>([]);
  const [selectedCommunity, setSelectedCommunity] = React.useState<string | null>(null);
  const [isFullscreen, setIsFullscreen] = React.useState(false);

  // 按社区过滤节点
  const filteredNodes = React.useMemo(() => {
    if (!selectedCommunity) return nodes;
    return nodes.filter((n) => n.community === selectedCommunity);
  }, [nodes, selectedCommunity]);

  // 只保留与过滤后节点相关的边
  const filteredEdges = React.useMemo(() => {
    if (!selectedCommunity) return edges;
    const nodeIds = new Set(filteredNodes.map((n) => n.id));
    return edges.filter(
      (e) => nodeIds.has(e.source) && nodeIds.has(e.target)
    );
  }, [edges, filteredNodes]);

  const nodeTypes = Array.from(new Set(nodes.map((n) => n.type))).sort();
  const edgeTypes = Array.from(new Set(edges.map((e) => e.type))).sort();

  return (
    <div
      className={`rounded-lg border overflow-hidden ${
        isFullscreen
          ? "fixed inset-0 z-50 rounded-none"
          : ""
      }`}
    >
      {/* 标题栏 */}
      <div className="flex items-center justify-between border-b px-4 py-2 bg-slate-50">
        <div className="flex items-center gap-2">
          <Network className="h-4 w-4 text-muted-foreground" />
          <span className="text-xs font-medium">
            知识图谱
            <span className="text-muted-foreground ml-2">
              ({nodes.length} 节点, {edges.length} 边)
            </span>
          </span>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setIsFullscreen(!isFullscreen)}
            className="text-[10px] text-muted-foreground hover:text-foreground transition-colors flex items-center gap-1"
          >
            {isFullscreen ? (
              <><Minimize2 className="h-3 w-3" />退出全屏</>
            ) : (
              <><Expand className="h-3 w-3" />全屏</>
            )}
          </button>
          <button
            onClick={onClose}
            className="text-[10px] text-muted-foreground hover:text-foreground transition-colors"
          >
            关闭图谱
          </button>
        </div>
      </div>

      {/* 社区筛选 */}
      {communities.length > 0 && (
        <div className="px-4 py-2 border-b bg-slate-50/50">
          <CommunityFilter
            communities={communities}
            selected={selectedCommunity}
            onSelect={setSelectedCommunity}
          />
        </div>
      )}

      {/* 类型过滤 */}
      {(nodeTypes.length > 0 || edgeTypes.length > 0) && (
        <div className="px-4 py-2 border-b bg-white flex flex-col gap-2">
          {nodeTypes.length > 0 && (
            <div className="flex items-center gap-1.5 flex-wrap">
              <span className="text-[10px] text-muted-foreground uppercase tracking-wider">节点</span>
              {nodeTypes.map((type) => {
                const active = visibleNodeTypes.length === 0 || visibleNodeTypes.includes(type);
                return (
                  <button
                    key={type}
                    onClick={() => {
                      setVisibleNodeTypes((prev) => {
                        if (prev.length === 0) return [type];
                        if (prev.includes(type)) {
                          const next = prev.filter((t) => t !== type);
                          return next.length === 0 ? [] : next;
                        }
                        return [...prev, type];
                      });
                    }}
                    className={`px-1.5 py-0.5 rounded text-[10px] border transition-colors ${
                      active
                        ? "bg-primary/10 text-primary border-primary/30"
                        : "bg-transparent text-muted-foreground border-border line-through"
                    }`}
                  >
                    {type}
                  </button>
                );
              })}
              {visibleNodeTypes.length > 0 && (
                <button
                  onClick={() => setVisibleNodeTypes([])}
                  className="text-[10px] text-muted-foreground hover:text-foreground"
                >
                  重置
                </button>
              )}
            </div>
          )}
          {edgeTypes.length > 0 && (
            <div className="flex items-center gap-1.5 flex-wrap">
              <span className="text-[10px] text-muted-foreground uppercase tracking-wider">关系</span>
              {edgeTypes.map((type) => {
                const active = visibleEdgeTypes.length === 0 || visibleEdgeTypes.includes(type);
                return (
                  <button
                    key={type}
                    onClick={() => {
                      setVisibleEdgeTypes((prev) => {
                        if (prev.length === 0) return [type];
                        if (prev.includes(type)) {
                          const next = prev.filter((t) => t !== type);
                          return next.length === 0 ? [] : next;
                        }
                        return [...prev, type];
                      });
                    }}
                    className={`px-1.5 py-0.5 rounded text-[10px] border transition-colors ${
                      active
                        ? "bg-primary/10 text-primary border-primary/30"
                        : "bg-transparent text-muted-foreground border-border line-through"
                    }`}
                  >
                    {type}
                  </button>
                );
              })}
              {visibleEdgeTypes.length > 0 && (
                <button
                  onClick={() => setVisibleEdgeTypes([])}
                  className="text-[10px] text-muted-foreground hover:text-foreground"
                >
                  重置
                </button>
              )}
            </div>
          )}
        </div>
      )}

      {/* 图谱画布 — 3D 赛博朋克 */}
      <CyberGraph3D
        nodes={filteredNodes}
        edges={filteredEdges}
        width={isFullscreen ? window.innerWidth : width}
        height={isFullscreen ? window.innerHeight - 120 : height}
        onNodeClick={onNodeClick}
      />
    </div>
  );
}
