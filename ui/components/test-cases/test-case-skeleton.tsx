/**
 * 版权所有 (c) 2023-2026 北京慧测信息技术有限公司(但问智能) 保留所有权利。
 * 
 * 本代码版权归北京慧测信息技术有限公司(但问智能)所有，仅用于学习交流目的，未经公司商业授权，
 * 不得用于任何商业用途，包括但不限于商业环境部署、售卖或以任何形式进行商业获利。违者必究。
 * 
 * 授权商业应用请联系微信：huice666
 */

import { cn } from "@/lib/utils";

interface SkeletonProps extends React.HTMLAttributes<HTMLDivElement> {
  /**
   * 是否显示动画
   * @default true
   */
  animate?: boolean;
}

function Skeleton({ className, animate = true, ...props }: SkeletonProps) {
  return (
    <div
      className={cn(
        "animate-pulse rounded-md bg-muted",
        !animate && "animate-none",
        className
      )}
      {...props}
    />
  );
}

interface TableRowSkeletonProps {
  /**
   * 行数
   * @default 5
   */
  rows?: number;
  /**
   * 是否显示复选框列
   * @default true
   */
  showCheckbox?: boolean;
}

/**
 * 表格行骨架屏
 */
export function TableRowSkeleton({
  rows = 5,
  showCheckbox = true,
}: TableRowSkeletonProps) {
  return (
    <>
      {Array.from({ length: rows }).map((_, i) => (
        <tr key={i} className="border-b">
          {showCheckbox && (
            <td className="p-3">
              <Skeleton className="h-4 w-4" />
            </td>
          )}
          <td className="p-3">
            <Skeleton className="h-4 w-20" />
          </td>
          <td className="p-3">
            <Skeleton className="h-4 w-full max-w-xs" />
          </td>
          <td className="p-3">
            <Skeleton className="h-5 w-16 rounded-full" />
          </td>
          <td className="p-3">
            <Skeleton className="h-5 w-16 rounded-full" />
          </td>
          <td className="p-3">
            <Skeleton className="h-4 w-24" />
          </td>
          <td className="p-3">
            <div className="flex gap-1">
              <Skeleton className="h-5 w-12 rounded-full" />
              <Skeleton className="h-5 w-12 rounded-full" />
            </div>
          </td>
          <td className="p-3">
            <Skeleton className="h-7 w-7" />
          </td>
        </tr>
      ))}
    </>
  );
}

interface TableHeaderSkeletonProps {
  /**
   * 是否显示复选框列
   * @default true
   */
  showCheckbox?: boolean;
}

/**
 * 表格头部骨架屏（用于过滤器区域）
 */
export function FilterBarSkeleton({ showCheckbox = true }: TableHeaderSkeletonProps) {
  return (
    <div className="flex items-center gap-3 border-b bg-muted/30 px-4 py-3">
      <Skeleton className="h-9 w-32" />
      <Skeleton className="h-9 w-32" />
      <Skeleton className="h-9 w-32" />
      <div className="flex-1" />
      <Skeleton className="h-9 w-24" />
    </div>
  );
}

export { Skeleton };
