"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  FolderKanban,
  FileText,
  PlayCircle,
  ClipboardList,
  BarChart3,
  ChevronDown,
  Settings,
  Home,
  Database,
  Globe,
  Server,
  Code2,
  Activity,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { ScrollArea } from "@/components/ui/scroll-area";
import type { ProjectInfo } from "@/lib/api/types";
import { useLanguage } from "@/providers/LanguageProvider";

interface SidebarProps {
  projects: ProjectInfo[];
  currentProject?: ProjectInfo | null;
  onProjectChange?: (project: ProjectInfo) => void;
}

export function Sidebar({
  projects,
  currentProject,
  onProjectChange,
}: SidebarProps) {
  const pathname = usePathname();
  const { t } = useLanguage();

  const navItems = [
    {
      title: t("nav.testCases"),
      href: "/test-cases",
      icon: FileText,
    },
    {
      title: t("nav.apiTests"),
      href: "/api-tests",
      icon: Database,
    },
    {
      title: t("nav.webTests"),
      href: "/web-tests",
      icon: Globe,
    },
    {
      title: t("nav.scenarioTests"),
      href: "/scenario-tests",
      icon: PlayCircle,
    },
    {
      title: t("nav.testRuns"),
      href: "/test-runs",
      icon: PlayCircle,
    },
    {
      title: t("nav.testPlans"),
      href: "/test-plans",
      icon: ClipboardList,
    },
    {
      title: t("nav.environments"),
      href: "/environments",
      icon: Server,
    },
    {
      title: "运行报告",
      href: "/dashboard",
      icon: BarChart3,
    },
    {
      title: "智能诊断",
      href: "/diagnosis",
      icon: Activity,
    },
    {
      title: "Allure 报告",
      href: "/allure-reports",
      icon: BarChart3,
    },
    {
      title: "全栈分析",
      href: "/fullstack-analysis",
      icon: Code2,
    },
  ];

  const getNavHref = (baseHref: string) => {
    if (!currentProject) return "#";
    return `/projects/${currentProject.identifier}${baseHref}`;
  };

  const isActive = (href: string) => {
    if (!currentProject) return false;
    const fullHref = getNavHref(href);
    return pathname.startsWith(fullHref);
  };

  return (
    <div className="flex h-full w-60 flex-col bg-sidebar text-sidebar-foreground">
      {/* Logo */}
      <div className="flex h-14 items-center border-b border-sidebar-border px-4">
        <Link href="/projects" className="flex items-center gap-2">
          <img src="/logo.svg" alt="logo" className="h-6 w-6" />
          <span className="font-semibold tracking-tight">{t("meta.title")}</span>
        </Link>
      </div>

      {/* Project Selector */}
      <div className="border-b border-sidebar-border p-3">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              variant="ghost"
              className="w-full justify-between border-sidebar-border bg-sidebar-accent text-sidebar-foreground hover:bg-sidebar-accent/80 hover:text-sidebar-foreground"
              disabled={projects.length === 0}
            >
              <span className="truncate">
                {currentProject?.name || t("nav.selectProject")}
              </span>
              <ChevronDown className="h-4 w-4 shrink-0 opacity-50" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent className="w-52">
            {projects.map((project) => (
              <DropdownMenuItem
                key={project.identifier}
                onClick={() => onProjectChange?.(project)}
                className={cn(
                  currentProject?.identifier === project.identifier &&
                    "bg-accent"
                )}
              >
                <span className="truncate">{project.name}</span>
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      {/* Navigation */}
      <ScrollArea className="flex-1 px-3 py-2">
        <nav className="flex flex-col gap-1">
          <Link href="/projects">
            <Button
              variant="ghost"
              className={cn(
                "w-full justify-start text-sidebar-foreground/70 hover:text-sidebar-foreground hover:bg-sidebar-accent transition-colors duration-200",
                pathname === "/projects" &&
                  "bg-sidebar-accent text-sidebar-foreground"
              )}
            >
              <Home className="mr-2 h-4 w-4" />
              {t("nav.allProjects")}
            </Button>
          </Link>

          {currentProject && (
            <>
              <div className="my-2 px-2 text-[10px] font-semibold uppercase tracking-wider text-sidebar-foreground/40">
                {t("nav.projectNavigation")}
              </div>
              {navItems.map((item) => (
                <Link key={item.href} href={getNavHref(item.href)}>
                  <Button
                    variant="ghost"
                    className={cn(
                      "group relative w-full justify-start text-sidebar-foreground/60 hover:text-sidebar-foreground hover:bg-sidebar-accent transition-all duration-200",
                      isActive(item.href) &&
                        "bg-sidebar-accent text-sidebar-foreground font-medium"
                    )}
                  >
                    {isActive(item.href) && (
                      <span className="absolute left-0 top-1/2 -translate-y-1/2 h-5 w-0.5 rounded-full bg-sky-500 transition-all duration-200" />
                    )}
                    <item.icon
                      className={cn(
                        "mr-2 h-4 w-4 transition-transform duration-200",
                        isActive(item.href) && "text-sky-400"
                      )}
                    />
                    {item.title}
                  </Button>
                </Link>
              ))}
            </>
          )}
        </nav>
      </ScrollArea>

      {/* Footer */}
      <div className="border-t border-sidebar-border p-3">
        <Button
          variant="ghost"
          className="w-full justify-start text-sidebar-foreground/60 hover:text-sidebar-foreground hover:bg-sidebar-accent transition-colors duration-200"
        >
          <Settings className="mr-2 h-4 w-4" />
          {t("nav.settings")}
        </Button>
      </div>
    </div>
  );
}
