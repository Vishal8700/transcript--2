/**
 * Minimal ambient Chrome Extension API declarations.
 * Provides just enough type coverage to silence IDE errors across the extension.
 * Full types: https://www.npmjs.com/package/@types/chrome
 */

declare namespace chrome {
  namespace runtime {
    function sendMessage(message: any, callback?: (response: any) => void): void
    function getManifest(): { version: string; [key: string]: any }
    function reload(): void
    const onMessage: {
      addListener(
        callback: (
          message: any,
          sender: chrome.runtime.MessageSender,
          sendResponse: (response?: any) => void
        ) => boolean | void
      ): void
    }
    const onUpdateAvailable: { addListener(callback: () => void): void }
    const onInstalled: { addListener(callback: () => void): void }
    interface MessageSender {
      tab?: chrome.tabs.Tab
      frameId?: number
      id?: string
      url?: string
    }
  }

  namespace storage {
    interface StorageArea {
      get(keys: string | string[] | null, callback: (items: any) => void): void
      set(items: object, callback?: () => void): void
    }
    const local: StorageArea
    const sync: StorageArea
    const onChanged: { addListener(callback: () => void): void }
  }

  namespace tabs {
    interface Tab {
      id?: number
      url?: string
    }
    function query(
      queryInfo: { active?: boolean; currentWindow?: boolean },
      callback: (tabs: Tab[]) => void
    ): void
    function create(properties: { url: string }): void
    const onRemoved: { addListener(callback: (tabId: number) => void): void }
  }

  namespace downloads {
    function download(
      options: { url: string; filename?: string; conflictAction?: string },
      callback?: (downloadId: number) => void
    ): Promise<number>
  }

  namespace scripting {
    function getRegisteredContentScripts(): Promise<any[]>
    function registerContentScripts(scripts: any[]): Promise<void>
    function unregisterContentScripts(filter?: any): Promise<void>
    function executeScript(injection: any): Promise<any>
  }

  namespace permissions {
    function request(permissions: {
      origins?: string[]
      permissions?: string[]
    }): Promise<boolean>
    function query(permissions: {
      origins?: string[]
      permissions?: string[]
    }): Promise<{ granted: boolean }>
    function contains(permissions: {
      origins?: string[]
      permissions?: string[]
    }): Promise<boolean>
    function remove(permissions: {
      origins?: string[]
      permissions?: string[]
    }): Promise<boolean>
    const onAdded: { addListener(callback: (permissions: any) => void): void }
  }

  namespace notifications {
    function create(
      notificationId: string,
      options: {
        type: string
        iconUrl: string
        title: string
        message: string
      },
      callback?: (id: string) => void
    ): void
    const onClicked: { addListener(callback: (id: string) => void): void }
  }

  namespace action {
    function openPopup(): Promise<void>
    function setIcon(details: { imageData?: any; path?: any }): void
  }

  namespace sidePanel {
    function open(options: { tabId?: number; windowId?: number }): Promise<void>
    function setOptions(options: any): void
  }

  namespace alarms {
    function create(name: string, alarmInfo: { periodInMinutes?: number }): void
    function get(name: string, callback: (alarm: any) => void): void
    const onAlarm: {
      addListener(callback: (alarm: { name: string }) => void): void
    }
  }
}
