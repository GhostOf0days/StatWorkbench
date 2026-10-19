// Keep local and CI test builds usable without signing credentials. Public
// version-tagged builds opt into hardened signing and macOS notarization via
// STATWORKBENCH_RELEASE_SIGNING=1; the workflow validates required secrets.
const releaseSigning = process.env.STATWORKBENCH_RELEASE_SIGNING === "1";

module.exports = {
  forceCodeSigning: releaseSigning,
  appId: "org.statworkbench.desktop",
  productName: "StatWorkbench",
  directories: {
    output: "release",
  },
  files: [
    "electron/**/*",
    "renderer-dist/**/*",
    "package.json",
    "LICENSE",
    "THIRD_PARTY_NOTICES.md",
    "licenses/**/*",
    "assets/statworkbench.png",
  ],
  extraResources: [
    {
      from: "dist-backend/statworkbench-engine",
      to: "engine",
    },
  ],
  asar: true,
  mac: {
    category: "public.app-category.education",
    target: ["dmg", "zip"],
    ...(releaseSigning
      ? { hardenedRuntime: true, notarize: true }
      : { identity: "-", hardenedRuntime: false }),
    extendInfo: {
      NSAppleEventsUsageDescription:
        "StatWorkbench reads the worksheets you select in Excel or Numbers and adds analysis results as new worksheets or workbooks.",
    },
    icon: "assets/statworkbench.icns",
  },
  win: {
    target: ["portable"],
    icon: "assets/statworkbench.ico",
    extraResources: [
      {
        from: "dist-windows/StatWorkbench.SpreadsheetBridge.exe",
        to: "spreadsheet-bridge/StatWorkbench.SpreadsheetBridge.exe",
      },
    ],
  },
  linux: {
    target: ["AppImage"],
    category: "Education;Science",
    icon: "assets/statworkbench.png",
  },
  beforePack: "scripts/verify-package-inputs.cjs",
};
