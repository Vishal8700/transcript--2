/** @type {Intl.DateTimeFormatOptions} */
export const TIMEFORMAT = {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: true
}

/** @type {Object<string, { id: string, js: string[], matches: string[], excludeMatches: string[], permissions: chrome.runtime.ManifestPermissions[] }>} */
export const PLATFORM_CONFIGS = {
    "google_meet": {
        id: "content-google-meet",
        js: [
            "content-scripts/common-config.js",
            "content-scripts/common-utils.js",
            "content-scripts/google-meet/config.js",
            "content-scripts/google-meet/utils.js",
            "content-scripts/google-meet/index.js"
        ],
        matches: ["https://meet.google.com/*"],
        excludeMatches: ["https://meet.google.com/", "https://meet.google.com/landing"],
        permissions: ["notifications"]
    },
    // Teams platform configuration is disabled.
}

export const ALARM_NAME = "dailyPermissionCheck"
export const INTERVAL_IN_MINUTES = 24 * 60 // 24 hours

