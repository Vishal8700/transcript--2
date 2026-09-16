import { getTranscriptString, getChatMessagesString } from "./utils.js"

const DEFAULT_ANALYSIS_URL = "http://127.0.0.1:8000/api/meetings/analyze"

/** Send the finished meeting to the private Python service for AI email reporting. */
export function sendMeetingToAnalysisServer(index) {
    return new Promise((resolve, reject) => {
        chrome.storage.local.get(["meetings"], (localResult) => {
            const meeting = localResult.meetings?.[index]
            if (!meeting) {
                reject(new Error("Meeting at index not found"))
                return
            }
            chrome.storage.sync.get(["analysisServerUrl", "autoEmailReportAfterMeeting"], (syncResult) => {
                if (syncResult.autoEmailReportAfterMeeting === false) {
                    resolve("AI email report disabled")
                    return
                }
                const payload = {
                    meetingSoftware: meeting.meetingSoftware || "Google Meet",
                    meetingTitle: meeting.meetingTitle || meeting.title || "Meeting",
                    meetingStartTimestamp: meeting.meetingStartTimestamp,
                    meetingEndTimestamp: meeting.meetingEndTimestamp,
                    transcript: getTranscriptString(meeting.transcript || []),
                    chatMessages: getChatMessagesString(meeting.chatMessages || [])
                }
                fetch(syncResult.analysisServerUrl || DEFAULT_ANALYSIS_URL, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(payload)
                }).then(async (response) => {
                    if (!response.ok) throw new Error(`Analysis server returned ${response.status}: ${await response.text()}`)
                    resolve("AI email report sent")
                }).catch(reject)
            })
        })
    })
}
