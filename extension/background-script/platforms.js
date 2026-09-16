import { PLATFORM_CONFIGS } from './config.js'

/**
 * @param {string|string[]} platform
 */
export function getPermissionStatus(platform) {
    /**
     * @param {string} p
     * @returns {Promise<string>}
     */
    function fetchSinglePlatformStatus(p) {
        return new Promise((resolve, reject) => {
            const config = PLATFORM_CONFIGS[p]

            if (!config) {
                reject(`Invalid platform: ${p}`)
                return
            }

            chrome.permissions.contains({
                origins: config.matches,
                permissions: config.permissions
            }).then(function (hasPermission) {
                if (hasPermission) {
                    resolve("Enabled")
                } else {
                    resolve("Disabled")
                }
            })
        })
    }

    if (Array.isArray(platform)) {
        // Multi-platform path
        return Promise.all(platform.map(function (p) {
            return fetchSinglePlatformStatus(p)
        }))
    } else {
        // Single platform path
        return fetchSinglePlatformStatus(platform)
    }
}


/**
 * @param {Platform|Platform[]} platform
 */
export function requestPlatformPermission(platform) {
    return new Promise((resolve, reject) => {
        const platforms = Array.isArray(platform) ? platform : [platform]

        // Map each platform to its config, then flatten the resulting nested arrays
        const allOrigins = platforms.flatMap(p => PLATFORM_CONFIGS[p]?.matches || [])
        const allPermissions = platforms.flatMap(p => PLATFORM_CONFIGS[p]?.permissions || [])

        // Use Set to handle duplicates
        const request = {
            origins: [...new Set(allOrigins)],
            permissions: [...new Set(allPermissions)]
        }

        chrome.permissions.request(request)
            .then((granted) => {
                granted ? resolve("Permissions granted") : reject("Permissions denied")
            })
            .catch((error) => {
                console.error(error)
                reject(`Could not get permissions for ${platforms.join(", ")}`)
            })
    })
}

/**
 * @param {Platform|Platform[]} platform
 */
export function getContentScriptStatus(platform) {
    /**
    * @param {string} p
    * @returns {Promise<string>}
    */
    function getSinglePlatformContentScriptStatus(p) {
        return new Promise((resolve, reject) => {
            const config = PLATFORM_CONFIGS[p]

            if (!config) {
                reject(`Invalid platform: ${p}`)
                return
            }

            chrome.scripting
                .getRegisteredContentScripts()
                .then((scripts) => {
                    const isRegistered = scripts.some(s => s.id === config.id)

                    if (isRegistered) {
                        resolve("Enabled")
                    } else {
                        resolve("Disabled")
                    }
                })
                .catch((error) => {
                    console.error(`Error fetching status for ${p}:`, error)
                    reject(`Could not retrieve status for ${p}`)
                })
        })
    }

    if (Array.isArray(platform)) {
        // Multi-platform path
        return Promise.all(platform.map(function (p) {
            return getSinglePlatformContentScriptStatus(p)
        }))
    } else {
        // Single platform path
        return getSinglePlatformContentScriptStatus(platform)
    }
}

/**
 * @param {Platform|Platform[]} platform
 */
export function registerContentScript(platform, showNotification = true) {
    /**
     * @param {string} p
     * @returns {Promise<string>}
     */
    function registerSinglePlatformContentScript(p) {
        return new Promise((resolve, reject) => {
            const config = PLATFORM_CONFIGS[p]

            // Map each match to a permission check
            const permissionChecks = config.matches.map(pattern =>
                chrome.permissions.contains({ origins: [pattern] }).then(result => result ? pattern : null)
            )

            Promise.all(permissionChecks).then((results) => {
                // Filter to get only patterns with existing permissions
                const allowedMatches = results.filter(pattern => pattern !== null)

                if (allowedMatches.length > 0) {
                    chrome.scripting
                        .getRegisteredContentScripts()
                        .then((scripts) => {
                            let isRegistered = scripts.some(s => s.id === config.id)

                            if (isRegistered) {
                                console.log(`${p} content script already registered`)
                                resolve(`Content script already registered`)
                            } else {
                                chrome.scripting.registerContentScripts([{
                                    id: config.id,
                                    js: config.js,
                                    matches: allowedMatches,
                                    excludeMatches: config.excludeMatches,
                                    runAt: "document_end",
                                }])
                                    .then(() => {
                                        console.log(`${p} content script registered successfully.`)

                                        if (showNotification) {
                                            chrome.permissions.contains({
                                                permissions: ["notifications"]
                                            }).then((hasNotifyPermission) => {
                                                if (hasNotifyPermission) {
                                                    chrome.notifications.create({
                                                        type: "basic",
                                                        iconUrl: "../icon.png",
                                                        title: "Enabled!",
                                                        message: `Refresh any existing meeting pages`
                                                    })
                                                }
                                            })
                                        }
                                        resolve(`Content script registered`)
                                    })
                                    .catch((error) => {
                                        console.error(`${p} registration failed.`, error)
                                        reject(`Failed to register content script`)
                                    })
                            }
                        })
                } else {
                    reject(`Insufficient permissions`)
                }
            })
        })
    }

    if (Array.isArray(platform)) {
        // Multi-platform path
        return Promise.all(platform.map(function (p) {
            return registerSinglePlatformContentScript(p)
        }))
    } else {
        // Single platform path
        return registerSinglePlatformContentScript(platform)
    }
}

/**
 * @param {Platform|Platform[]} platform
 */
export function deregisterContentScript(platform) {
    /**
    * @param {string} p
    * @returns {Promise<string>}
    */
    function deregisterSinglePlatformContentScript(p) {
        return new Promise((resolve, reject) => {
            const config = PLATFORM_CONFIGS[p]

            chrome.scripting
                .getRegisteredContentScripts()
                .then((scripts) => {
                    let isRegistered = scripts.some(s => s.id === config.id)

                    if (!isRegistered) {
                        console.log(`${p} content script not registered`)
                        resolve(`Content script not registered`)
                    } else {
                        chrome.scripting.unregisterContentScripts({
                            ids: [config.id]
                        })
                            .then(() => {
                                console.log(`${p} content script deregistered successfully.`)
                                resolve(`Content script deregistered`)
                            })
                            .catch((error) => {
                                console.error(`${p} deregistration failed.`, error)
                                reject(`Failed to deregister content script`)
                            })
                    }
                })
        })
    }

    if (Array.isArray(platform)) {
        // Multi-platform path
        return Promise.all(platform.map(function (p) {
            return deregisterSinglePlatformContentScript(p)
        }))
    } else {
        // Single platform path
        return deregisterSinglePlatformContentScript(platform)
    }
}


export function reRegisterContentScripts() {
    chrome.storage.sync.get(["wantGoogleMeet"], function (resultSyncUntyped) {
        const resultSync = /** @type {ResultSync} */ (resultSyncUntyped)

        /** @type {Promise<any>[]} */
        const reRegisterPromises = []

        /** @type {Platform[]} */
        const wantedPlatforms = []

        // Register content scripts if permissions are available and if user has not explicitly opted out
        if (resultSync.wantGoogleMeet) {
            wantedPlatforms.push("google_meet")
        }
        // Teams re-registration is disabled.

        if (wantedPlatforms.length > 0) {
            reRegisterPromises.push(registerContentScript(wantedPlatforms, false))
        }

        Promise.all(reRegisterPromises)
            .then(() => {
                console.log("Permitted scripts re-registered successfully.")
            })
            .catch((error) => {
                console.log(error)
            })
    })
}