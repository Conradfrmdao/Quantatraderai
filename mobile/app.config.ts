import type { ExpoConfig } from "@expo/config-types";

const config: ExpoConfig = {
  name: "QuntaTradeAI",
  slug: "quntatradeai",
  version: "1.0.0",
  orientation: "portrait",
  icon: "./assets/icon.png",
  splash: { image: "./assets/splash.png", resizeMode: "contain", backgroundColor: "#000000" },
  assetBundlePatterns: ["**/*"],
  ios:     { supportsTablet: true, bundleIdentifier: "com.quntatrade.app" },
  android: { adaptiveIcon: { foregroundImage: "./assets/adaptive-icon.png", backgroundColor: "#000000" }, package: "com.quntatrade.app" },
  web:     { favicon: "./assets/favicon.png" },
  extra: {
    eas: { projectId: "your-eas-project-id" },
  },
  plugins: [
    "expo-router",
    "expo-secure-store",
    ["expo-notifications", { icon: "./assets/notification-icon.png", color: "#000000" }],
  ],
  scheme: "quntatrade",
};

export default config;
