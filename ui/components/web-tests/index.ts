/**
 * 版权所有 (c) 2023-2026 北京慧测信息技术有限公司(但问智能) 保留所有权利。
 * 
 * 本代码版权归北京慧测信息技术有限公司(但问智能)所有，仅用于学习交流目的，未经公司商业授权，
 * 不得用于任何商业用途，包括但不限于商业环境部署、售卖或以任何形式进行商业获利。违者必究。
 * 
 * 授权商业应用请联系微信：huice666
 */
// eslint-disable  MC8yOmFIVnBZMlhwbVlqbHJvL3BuYWs2TVRWMmR3PT06MTEwNzlhOGI=

// Web 功能相关组件
export { WebFunctionFolderTree } from "./folder-tree";
export type { WebFunctionFolderTreeRef } from "./folder-tree";
export { WebSubFunctionSidebar } from "./web-function-sidebar";

// Web 页面相关组件 (保留原有的)
export { WebPageList } from "./web-page-list";
export { WebPageSidebar } from "./web-page-sidebar";

// 新增的 Web 测试组件
export { CreateWebFunctionDialog } from "./create-function-dialog";
export { AIGenerateDialog } from "./ai-generate-dialog";
export { WebFunctionList } from "./web-function-list";
export { WebSubFunctionList } from "./web-sub-function-list";
export { EnhancedTestArtifactsPanel } from "./test-artifacts-panel-enhanced";
// NOTE  MS8yOmFIVnBZMlhwbVlqbHJvL3BuYWs2TVRWMmR3PT06MTEwNzlhOGI=

// 为了向后兼容，保留旧的导出
export { WebFolderTree } from "./folder-tree";
