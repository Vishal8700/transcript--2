/**
 * @description State Factory: Returns a pristine, isolated meeting state block.
 * @param {MeetingSoftware} meetingSoftware
 * @param {Platform} platform
 * @returns {ContentScriptState}
 */
function createContentScriptState(meetingSoftware, platform) {
    return {
        meetingSoftware: meetingSoftware,
        platform: platform,
        userName: "You",
        transcript: [],
        chatMessages: [],
        stateTranscriptBlock: {
            timestamp: "",
            mutationTargetElement: null,
            personName: "",
            transcriptTextBuffer: "",

        },
        meetingStartTimestamp: new Date().toISOString(),
        meetingTitle: document.title,
        transcriptTargetNode: null,
        transcriptObserver: null,
        chatMessagesTargetNode: null,
        chatMessagesObserver: null,
        isTranscriptDomErrorCaptured: false,
        isChatMessagesDomErrorCaptured: false,
        hasMeetingStarted: false,
        hasMeetingEnded: false,
        extensionStatusJSON: {
            status: 200,
            message: "<strong>Transcriber is running</strong> <br /> Do not turn off captions"
        },
        // Tracks already-dispatched automation commands so each fires exactly once
        dispatchedCommands: new Set()
    }
}

/**
 * @description Fetches extension status from GitHub and saves to chrome storage. Defaults to 200, if remote server is unavailable.
 * @param {ContentScriptState} state
 */
function checkExtensionStatus(state) {
    return new Promise((resolve, reject) => {
        // Set default value as 200
        state.extensionStatusJSON = {
            status: 200,
            message: state.meetingSoftware ? NOTIFICATION_PLATFORM_CONFIGS[state.platform].notificationText : ""
        }

        // https://stackoverflow.com/a/42518434
        fetch(
            state.meetingSoftware ? NOTIFICATION_PLATFORM_CONFIGS[state.platform].statusUrl : "",
            { cache: "no-store" }
        )
            .then((response) => response.json())
            .then((result) => {
                state.extensionStatusJSON.status = result.status
                state.extensionStatusJSON.message = result.message
                state.extensionStatusJSON.showBetaMessage = (result.showBetaMessage === true)

                console.log("Extension status fetched and saved")
                resolve("Extension status fetched and saved")
            })
            .catch((err) => {
                console.error(err)
                reject("Could not fetch extension status")

                logError(state, "008", err)
            })
    })
}

/**
 * @description Overwrite state to chrome storage
 * @param {ContentScriptState} state
 * @param {Array<"meetingSoftware"  | "meetingTitle" | "meetingStartTimestamp" | "transcript" | "chatMessages">} keys
 * @param {boolean} sendDownloadMessage
 */
function overWriteChromeStorage(state, keys, sendDownloadMessage) {
    const objectToSave = {}
    if (keys.includes("meetingSoftware")) objectToSave.meetingSoftware = state.meetingSoftware
    if (keys.includes("meetingTitle")) objectToSave.meetingTitle = state.meetingTitle
    if (keys.includes("meetingStartTimestamp")) objectToSave.meetingStartTimestamp = state.meetingStartTimestamp
    if (keys.includes("transcript")) objectToSave.transcript = state.transcript
    if (keys.includes("chatMessages")) objectToSave.chatMessages = state.chatMessages

    chrome.storage.local.set(objectToSave, function () {
        if (sendDownloadMessage) {
            /** @type {ExtensionMessage} */
            const message = { type: "meeting_ended" }
            chrome.runtime.sendMessage(message, (responseUntyped) => {
                const response = /** @type {ExtensionResponse} */ (responseUntyped)
                if ((!response.success)) {
                    const parsedError = /** @type {ErrorObject} */ (response.message)
                    if (parsedError.errorCode === "010") {
                        console.error(parsedError.errorMessage)
                    }
                }
            })
        }
    })
}

/**
 * @description Attempts to recover last meeting to the best possible extent.
 */
function recoverLastMeeting() {
    return new Promise((resolve, reject) => {
        /** @type {ExtensionMessage} */
        const message = {
            type: "recover_last_meeting",
        }
        chrome.runtime.sendMessage(message, function (responseUntyped) {
            const response = /** @type {ExtensionResponse} */ (responseUntyped)
            if (response.success) {
                resolve("Last meeting recovered successfully or recovery not needed")
            }
            else {
                reject(response.message)
            }
        })
    })
}

/**
 * @description Efficiently waits until the element of the specified selector and textContent appears in the DOM. Polls only on animation frame change
 * @param {string} selector
 * @param {string | RegExp} [text]
 * @param {HTMLIFrameElement | null} iframe
 */
async function waitForElement(selector, text, iframe = null) {
    // If an iframe is provided, use its content document; otherwise, default to top-level document
    const targetDoc = iframe ? /** @type {Document} */ (iframe.contentDocument) : document

    if (text) {
        // loops for every animation frame change, until the required element is found
        while (!Array.from(targetDoc.querySelectorAll(selector)).find(element => element.textContent === text)) {
            await new Promise((resolve) => requestAnimationFrame(resolve))
        }
    }
    else {
        // loops for every animation frame change, until the required element is found
        while (!targetDoc.querySelector(selector)) {
            await new Promise((resolve) => requestAnimationFrame(resolve))
        }
    }
    return targetDoc.querySelector(selector)
}

/**
 * @description Waits until an element matching the selector has the specified computed CSS property value.
 * @param {string} selector - The selector to query (e.g., 'div[role="region"]')
 * @param {string} cssProp - The camelCase or kebab-case CSS property (e.g., 'containerName')
 * @param {string} cssPropValue - The expected value of the CSS property (e.g., 'captions-history')
 */
async function waitForElementByStyle(selector, cssProp, cssPropValue) {
    while (true) {
        const elements = Array.from(document.querySelectorAll(selector))
        const matchedElement = elements.find(element => {
            const computedStyle = window.getComputedStyle(element)
            // Cast the string to a valid key type of CSSStyleDeclaration to satisfy the compiler
            return computedStyle[/** @type {keyof CSSStyleDeclaration} */ (cssProp)] === cssPropValue
        })

        if (matchedElement) {
            return matchedElement
        }

        await new Promise((resolve) => requestAnimationFrame(resolve))
    }
}

/** 
 * @description Single, flat polling monitor that handles initial attachment and all re-attachments.
 * @param {ContentScriptState} state
 */
function startTranscriptMonitor(state) {
    state.transcriptTargetNode = null
    /**
     * @type {number | undefined}
     */
    let monitorInterval = undefined

    // Call immediately
    transcriptMonitor()
    // Start monitoring
    monitorInterval = setInterval(transcriptMonitor, 2000)

    function transcriptMonitor() {
        if (state.hasMeetingEnded) {
            clearInterval(monitorInterval)
            return
        }

        let activeNode

        switch (state.platform) {
            case "google_meet":
                activeNode = document.querySelector(SELECTORS_GOOGLE_MEET.TRANSCRIPT_REGION)
                break
            // Teams transcript regions are disabled.
            default:
                break
        }

        if (!activeNode) {
            return
        }

        // If the active node is new, replaced, or disconnected, re-attach the observer
        if (!state.transcriptTargetNode || activeNode !== state.transcriptTargetNode || !state.transcriptTargetNode.isConnected) {
            if (!state.transcriptTargetNode) {
                console.log("Captions region detected. Attaching observer...")
            }
            else if (activeNode !== state.transcriptTargetNode) {
                console.log("Captions region replaced. Re-attaching observer...")
            }

            // Flush any in-flight buffer to prevent losing text on transitions
            pushBufferToTranscript(state)
            state.stateTranscriptBlock.personName = ""
            state.stateTranscriptBlock.transcriptTextBuffer = ""
            state.stateTranscriptBlock.timestamp = ""

            if (state.transcriptObserver) {
                state.transcriptObserver.disconnect()
            }

            state.transcriptTargetNode = activeNode
            state.transcriptObserver = new MutationObserver((mutations) => {
                switch (state.platform) {
                    case "google_meet":
                        transcriptMutationCallbackGoogleMeet(state, mutations)
                        break
                    // Teams transcript callbacks are disabled.
                    default:
                        break
                }
            })
            state.transcriptObserver.observe(activeNode, mutationConfig)

            // If specified, hide the whole transcript node
            chrome.storage.sync.get(["hideCaptions"], function (resultSyncUntyped) {
                const resultSync = /** @type {ResultSync} */ (resultSyncUntyped)
                if ((resultSync.hideCaptions === true) && (state.transcriptTargetNode)) {
                    state.transcriptTargetNode.setAttribute("style", `opacity:0; height:0px`)
                }
            })
        }
    }
}

/**
 * @param {ContentScriptState} state
 */
function broadcastLiveBuffer(state) {
    /** @type {ExtensionMessage} */
    const message = {
        type: "broadcast_live_buffer",
        stateTranscriptBlock: {
            mutationTargetElement: null,
            personName: state.stateTranscriptBlock.personName,
            timestamp: state.stateTranscriptBlock.timestamp,
            transcriptTextBuffer: state.stateTranscriptBlock.transcriptTextBuffer
        }
    }
    chrome.runtime.sendMessage(message, () => { })
}

/**
 * @param {ContentScriptState} state
 */
function pushBufferToTranscript(state) {
    if ((state.stateTranscriptBlock.personName !== "") && (state.stateTranscriptBlock.transcriptTextBuffer !== "")) {
        state.transcript.push({
            "personName": state.stateTranscriptBlock.personName === "You" ? state.userName : state.stateTranscriptBlock.personName,
            "timestamp": state.stateTranscriptBlock.timestamp,
            "transcriptText": state.stateTranscriptBlock.transcriptTextBuffer
        })
        overWriteChromeStorage(state, ["transcript"], false)
    }
}

/**
 * @description Waits and grabs meeting title from document title
 * @param {ContentScriptState} state
 */
function updateMeetingTitle(state) {
    setTimeout(() => {
        // NON CRITICAL DOM DEPENDENCY
        state.meetingTitle = document.title
        overWriteChromeStorage(state, ["meetingTitle"], false)
    }, 5000)
}

function pulseStatus() {
    const statusActivityCSS = `position: fixed;
    top: 0px;
    width: 100%;
    height: 4px;
    z-index: 100;
    transition: background-color 0.3s ease-in
  `
    /** @type {HTMLDivElement | null}*/
    let activityStatus = document.querySelector(`#transcriptonic-status`)
    if (!activityStatus) {
        let html = document.querySelector("html")
        activityStatus = document.createElement("div")
        activityStatus.setAttribute("id", "transcriptonic-status")
        activityStatus.style.cssText = `background-color: #2A9ACA; ${statusActivityCSS}`
        html?.appendChild(activityStatus)
    }
    else {
        activityStatus.style.cssText = `background-color: #2A9ACA; ${statusActivityCSS}`
    }

    setTimeout(() => {
        activityStatus.style.cssText = `background-color: transparent; ${statusActivityCSS}`
    }, 3000)
}

function renderFab() {
    const fabCss = `
        position: fixed;
        top: 50%;
        bottom: 50%;
        right: 8px;
        height: 36px;
        width: 36px;
        border-radius: 36px;
        z-index: 100;
        display: flex;
        align-items: center;
        justify-content: center;
        background-color: #071f29;
        box-shadow: 0px 0px 4px 0px #2A9ACA;
        cursor: pointer;
        border: none;
        padding: 0;
        overflow: visible;
    `

    const html = document.querySelector("html")
    const fab = document.createElement("button")
    fab.id = "transcriptonic-fab"
    fab.ariaLabel = "Transcriber"
    fab.title = "Transcriber"
    fab.style.cssText = fabCss

    // Use the local extension icon — avoids Cross-Origin-Resource-Policy errors
    // that occur when loading external URLs from a content script context.
    const logoUrl = chrome.runtime.getURL("icon.png")

    fab.innerHTML = `
        <div id="fab-main-content" style="display: flex; align-items: center; justify-content: center; width: 100%; height: 100%;">
            <img id="fab-default-logo" src="${logoUrl}" alt="Transcriber" draggable="false" style="width: 20px; height: 20px; object-fit: contain;" />
            <span id="fab-letter-mark" style="display: none; color: #ffffff; font-weight: bold; font-size: 16px; text-transform: uppercase; font-family: sans-serif;"></span>
        </div>

        <img id="fab-mini-badge" src="${logoUrl}" alt="Active Badge" draggable="false" style="
            display: none;
            position: absolute;
            bottom: -2px;
            right: -2px;
            width: 14px;
            height: 14px;
            border-radius: 50%;
            background-color: #071f29;
            box-shadow: 0 0 2px rgba(0,0,0,0.5);
            object-fit: contain;
            pointer-events: none;
        " />
    `

    html?.appendChild(fab)
    makeVerticallyDraggable(fab)

    fab.addEventListener("click", () => {
        /** @type {ExtensionMessage} */
        const message = { type: "open_side_panel" }
        chrome.runtime.sendMessage(message, () => { })
    })

    // Initial storage query on load
    chrome.storage.local.get(["transcript"], (resultUntyped) => {
        const result = /** @type {ResultLocal} */ (resultUntyped)
        updateFabState(result.transcript)
    })
}

/**
 * @param {HTMLButtonElement} fab
 */
function makeVerticallyDraggable(fab) {
    let isDragging = false
    let startY = 0
    let initialTop = 0
    let hasMoved = false

    const onPointerDown = (e) => {
        isDragging = true
        hasMoved = false

        const clientY = e.touches ? e.touches[0].clientY : e.clientY
        startY = clientY
        initialTop = fab.getBoundingClientRect().top

        // Attach movement listeners to document so fast drags aren't lost
        document.addEventListener("mousemove", onPointerMove)
        document.addEventListener("mouseup", onPointerUp)
        document.addEventListener("touchmove", onPointerMove, { passive: false })
        document.addEventListener("touchend", onPointerUp)
    }

    const onPointerMove = (e) => {
        if (!isDragging) return

        const clientY = e.touches ? e.touches[0].clientY : e.clientY
        const deltaY = clientY - startY

        // Threshold (3px) to differentiate click from drag
        if (Math.abs(deltaY) > 3) {
            hasMoved = true
            if (e.cancelable) e.preventDefault() // Prevent scrolling on touch
        }

        let newTop = initialTop + deltaY

        // Bound vertical position inside the visible viewport
        const maxTop = window.innerHeight - fab.offsetHeight
        newTop = Math.max(0, Math.min(newTop, maxTop))

        fab.style.top = `${newTop}px`
    }

    const onPointerUp = () => {
        isDragging = false
        document.removeEventListener("mousemove", onPointerMove)
        document.removeEventListener("mouseup", onPointerUp)
        document.removeEventListener("touchmove", onPointerMove)
        document.removeEventListener("touchend", onPointerUp)
    }

    fab.addEventListener("mousedown", onPointerDown)
    fab.addEventListener("touchstart", onPointerDown, { passive: true })

    // Block the 'click' event if the user dragged the button
    fab.addEventListener("click", (e) => {
        if (hasMoved) {
            e.stopImmediatePropagation()
            e.preventDefault()
            hasMoved = false
        }
    }, true) // Capture phase ensures it runs before the side-panel click handler
}

/**
 * Updates the FAB visual state based on the current transcript data.
 * @param {ContentScriptState} state
 */
function updateFabState(state) {
    const fab = document.querySelector("#transcriptonic-fab")

    const defaultLogo = fab?.querySelector("#fab-default-logo")
    const letterMark = fab?.querySelector("#fab-letter-mark")
    const miniBadge = fab?.querySelector("#fab-mini-badge")

    if (state.transcript && state.transcript.length > 0) {
        const currentSpeaker = state.stateTranscriptBlock?.personName

        if (currentSpeaker && currentSpeaker.trim() !== "") {
            const initial = currentSpeaker.trim().charAt(0)

            // Active Speaker State: Show letter mark + corner badge, hide central logo
            if (defaultLogo) defaultLogo.style.display = "none"
            if (letterMark) {
                letterMark.textContent = initial
                letterMark.style.display = "inline"
            }
            if (miniBadge) miniBadge.style.display = "block"
            return
        }
    }

    // Default State: Fallback to central logo, hide mark + badge
    if (defaultLogo) defaultLogo.style.display = "block"
    if (letterMark) letterMark.style.display = "none"
    if (miniBadge) miniBadge.style.display = "none"
}

function unmountFab() {
    const fab = document.querySelector("#transcriptonic-fab")
    if (fab) {
        fab.remove()
    }
}

/**
   * @description Logs active transcript to console
   * @param {ContentScriptState} state
   */
function logTranscriptToConsole(state) {
    if (state.stateTranscriptBlock.transcriptTextBuffer.length > 125) {
        console.log(state.stateTranscriptBlock.transcriptTextBuffer.slice(0, 50) + "   ...   " + state.stateTranscriptBlock.transcriptTextBuffer.slice(-50))
    }
    else {
        console.log(state.stateTranscriptBlock.transcriptTextBuffer)
    }
}

/**
   * @description Logs anonymous errors to a Google sheet for swift debugging
   * @param {ContentScriptState} state
   * @param {string} code
   * @param {any} err
   */
function logError(state, code, err) {
    fetch(`${LOG_ERROR_SCRIPT_URL}?version=${chrome.runtime.getManifest().version}&code=${code}&error=${encodeURIComponent(err)}&meetingSoftware=${state.meetingSoftware}`, { mode: "no-cors" })
}

