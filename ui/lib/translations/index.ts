/**
 * 版权所有 (c) 2023-2026 北京慧测信息技术有限公司(但问智能) 保留所有权利。
 * 
 * 本代码版权归北京慧测信息技术有限公司(但问智能)所有，仅用于学习交流目的，未经公司商业授权，
 * 不得用于任何商业用途，包括但不限于商业环境部署、售卖或以任何形式进行商业获利。违者必究。
 * 
 * 授权商业应用请联系微信：huice666
 */

import { translations as zhTranslations } from "./zh";
import { translations as enTranslations } from "./en";
import { translations as jaTranslations } from "./ja";

export type Language = "zh" | "en" | "ja";

export const translations = {
  zh: zhTranslations,
  en: enTranslations,
  ja: jaTranslations,
};

export const languageNames: Record<Language, string> = {
  zh: "中文",
  en: "English",
  ja: "日本語",
};

/**
 * 获取当前语言（从 localStorage 读取）
 * 这个函数可以在非 React 组件中使用
 */
export function getCurrentLanguage(): Language {
  if (typeof window === "undefined") {
    return "zh"; // SSR 默认中文
  }
  const stored = localStorage.getItem("app-language");
  return (stored as Language) || "zh";
}

// 获取翻译文本的工具函数
export function getTranslation(
  language: Language,
  key: string,
  params?: Record<string, string>
): string {
  const keys = key.split(".");
  let value: any = translations[language];

  for (const k of keys) {
    if (value && typeof value === "object" && k in value) {
      value = value[k];
    } else {
      console.warn(`Translation key not found: ${key} for language: ${language}`);
      // 回退到中文
      if (language !== "zh") {
        return getTranslation("zh", key, params);
      }
      return key;
    }
  }

  if (typeof value !== "string") {
    return key;
  }

  // 参数替换
  if (params) {
    return value.replace(/\{(\w+)\}/g, (match, paramKey) => {
      return params[paramKey] || match;
    });
  }

  return value;
}

/**
 * 翻译函数（自动使用当前语言）
 * 可以在非 React 组件中使用
 * @param key 翻译键
 * @param params 参数对象
 * @returns 翻译后的文本
 */
export function t(key: string, params?: Record<string, string>): string {
  return getTranslation(getCurrentLanguage(), key, params);
}

export { zhTranslations, enTranslations, jaTranslations };

