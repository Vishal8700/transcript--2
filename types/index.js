// @ts-check
/**
 * @fileoverview Shared JSDoc type definitions for the Transcriber Chrome extension.
 * Included via jsconfig.json so all extension JS files can reference these types
 * without needing individual /// <reference> directives.
 */

/**
 * @typedef {"google_meet" | "teams"} Platform
 */

/**
 * @typedef {"Google Meet" | "Teams"} MeetingSoftware
 */

/**
 * @typedef {Object} TranscriptBlock
 * @property {string} personName
 * @property {string} timestamp
 * @property {string} transcriptText
 */

/**
 * @typedef {Object} ChatMessage
 * @property {string} personName
 * @property {string} timestamp
 * @property {string} chatMessageText
 */

/**
 * @typedef {Object} Meeting
 * @property {string} meetingSoftware
 * @property {string} meetingTitle
 * @property {string} meetingStartTimestamp
 * @property {string} meetingEndTimestamp
 * @property {TranscriptBlock[]} transcript
 * @property {ChatMessage[]} chatMessages
 * @property {"new" | "successful" | "failed"} webhookPostStatus
 * @property {string} [title]
 */

/**
 * @typedef {Object} StateTranscriptBlock
 * @property {string} timestamp
 * @property {Element | null} mutationTargetElement
 * @property {string} personName
 * @property {string} transcriptTextBuffer
 */

/**
 * @typedef {Object} ExtensionStatusJSON
 * @property {200 | 400} status
 * @property {string} message
 */

/**
 * @typedef {Object} ContentScriptState
 * @property {MeetingSoftware} meetingSoftware
 * @property {Platform} platform
 * @property {string} userName
 * @property {TranscriptBlock[]} transcript
 * @property {ChatMessage[]} chatMessages
 * @property {StateTranscriptBlock} stateTranscriptBlock
 * @property {string} meetingStartTimestamp
 * @property {string} meetingTitle
 * @property {Element | null} transcriptTargetNode
 * @property {MutationObserver | null} transcriptObserver
 * @property {Element | null} chatMessagesTargetNode
 * @property {MutationObserver | null} chatMessagesObserver
 * @property {boolean} isTranscriptDomErrorCaptured
 * @property {boolean} isChatMessagesDomErrorCaptured
 * @property {boolean} hasMeetingStarted
 * @property {boolean} hasMeetingEnded
 * @property {ExtensionStatusJSON} extensionStatusJSON
 * @property {Set<string>} dispatchedCommands
 */

/**
 * @typedef {Object} ExtensionMessage
 * @property {string} type
 * @property {number} [index]
 * @property {Platform | Platform[]} [platform]
 * @property {string} [command]
 */

/**
 * @typedef {Object} ExtensionResponse
 * @property {boolean} success
 * @property {any} [message]
 * @property {string} [issueUrl]
 * @property {string} [webLink]
 * @property {string} [error]
 */

/**
 * @typedef {Object} ErrorObject
 * @property {string} errorCode
 * @property {string} errorMessage
 */

/**
 * @typedef {Object} ResultLocal
 * @property {Meeting[]} [meetings]
 * @property {string} [meetingTabId]
 * @property {string} [meetingSoftware]
 * @property {string} [meetingTitle]
 * @property {string} [meetingStartTimestamp]
 * @property {TranscriptBlock[]} [transcript]
 * @property {ChatMessage[]} [chatMessages]
 * @property {boolean} [isDeferredUpdatedAvailable]
 */

/**
 * @typedef {Object} ResultSync
 * @property {string} [webhookUrl]
 * @property {boolean} [autoPostWebhookAfterMeeting]
 * @property {boolean} [autoDownloadFileAfterMeeting]
 * @property {"simple" | "advanced"} [webhookBodyType]
 * @property {"auto" | "manual"} [operationMode]
 * @property {boolean} [hideCaptions]
 * @property {boolean} [wantGoogleMeet]
 * @property {boolean} [autoEmailReportAfterMeeting]
 * @property {string} [analysisServerUrl]
 */

/**
 * @typedef {Object} WebhookBody
 * @property {"simple" | "advanced"} webhookBodyType
 * @property {string} meetingSoftware
 * @property {string} meetingTitle
 * @property {string} meetingStartTimestamp
 * @property {string} meetingEndTimestamp
 * @property {string | TranscriptBlock[]} transcript
 * @property {string | ChatMessage[]} chatMessages
 */
