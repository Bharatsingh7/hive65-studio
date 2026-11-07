"""App notifications (Discord, WhatsApp, ...).

Windows: WinRT UserNotificationListener. The first run asks for permission
(Settings > Privacy > Notifications must allow apps to access notifications).
Linux: eavesdrop org.freedesktop.Notifications.Notify on the session bus
(works with mako, dunst, swaync on Hyprland) via dbus-next.
"""
import asyncio

from . import LINUX, WINDOWS, Source


class WindowsNotifications(Source):
    name = "apps"
    interval = 1.0

    def setup(self):
        from winrt.windows.ui.notifications import NotificationKinds
        from winrt.windows.ui.notifications.management import (
            UserNotificationListener, UserNotificationListenerAccessStatus)
        self.kinds = NotificationKinds.TOAST
        self.listener = UserNotificationListener.current
        self.loop = asyncio.new_event_loop()
        status = self.loop.run_until_complete(self.listener.request_access_async())
        if status != UserNotificationListenerAccessStatus.ALLOWED:
            raise PermissionError("notification access denied: allow it in Windows Settings > "
                                  "Privacy & security > Notifications")
        self.seen = {n.id for n in self._fetch()}

    def _fetch(self):
        return list(self.loop.run_until_complete(self.listener.get_notifications_async(self.kinds)))

    def poll(self):
        for n in self._fetch():
            if n.id in self.seen:
                continue
            self.seen.add(n.id)
            try:
                app = n.app_info.display_info.display_name
            except Exception:
                app = "app"
            self.emit("app", None, app=app)


class LinuxNotifications(Source):
    name = "apps"

    def run(self):
        try:
            asyncio.run(self._main())
        except Exception as e:
            self.error = f"apps: {e}"

    async def _main(self):
        from dbus_next import Message, MessageType
        from dbus_next.aio import MessageBus
        bus = await MessageBus().connect()
        rule = "type='method_call',interface='org.freedesktop.Notifications',member='Notify'"
        reply = await bus.call(Message(destination="org.freedesktop.DBus",
                                       path="/org/freedesktop/DBus",
                                       interface="org.freedesktop.DBus.Monitoring",
                                       member="BecomeMonitor", signature="asu",
                                       body=[[rule], 0]))
        if reply.message_type == MessageType.ERROR:
            raise RuntimeError(reply.body)

        def handler(msg):
            if msg.member == "Notify" and msg.body:
                self.emit("app", None, app=str(msg.body[0]))

        bus.add_message_handler(handler)
        while not self.stopped.is_set():
            await asyncio.sleep(0.5)


def create(emit):
    if WINDOWS:
        return WindowsNotifications(emit)
    if LINUX:
        return LinuxNotifications(emit)
    return None
