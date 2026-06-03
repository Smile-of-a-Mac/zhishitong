export const NOTIFICATIONS_REFRESH_EVENT = 'zhishitong:notifications-refresh'

export function notifyNotificationsChanged() {
  window.dispatchEvent(new Event(NOTIFICATIONS_REFRESH_EVENT))
}
