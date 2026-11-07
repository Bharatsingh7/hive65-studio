"""Track changes, with colours from the album art.

Windows: WinRT GlobalSystemMediaTransportControls (Spotify, browsers, ...).
Linux: MPRIS PropertiesChanged on the session bus via dbus-next.
"""
import asyncio
import io

from . import LINUX, WINDOWS, Source


def _art_colors(data):
    try:
        from PIL import Image

        from ..ambient.palette import extract
        return extract(Image.open(io.BytesIO(data)), 5)
    except Exception:
        return None


class WindowsMedia(Source):
    name = "media"
    interval = 1.0

    def setup(self):
        from winrt.windows.media.control import (
            GlobalSystemMediaTransportControlsSessionManager as Manager)
        self.loop = asyncio.new_event_loop()
        self.manager = self.loop.run_until_complete(Manager.request_async())
        self.last = self._track()[0]

    def _track(self):
        s = self.manager.get_current_session()
        if not s:
            return None, None
        props = self.loop.run_until_complete(s.try_get_media_properties_async())
        return (props.title, props.artist), props

    def _thumbnail(self, props):
        from winrt.windows.storage.streams import Buffer, InputStreamOptions
        if not props.thumbnail:
            return None
        stream = self.loop.run_until_complete(props.thumbnail.open_read_async())
        buf = Buffer(stream.size)
        self.loop.run_until_complete(stream.read_async(buf, buf.capacity, InputStreamOptions.READ_AHEAD))
        return bytes(buf)

    def poll(self):
        track, props = self._track()
        if track and track != self.last and track[0]:
            self.last = track
            colors = None
            try:
                data = self._thumbnail(props)
                colors = _art_colors(data) if data else None
            except Exception:
                pass
            self.emit("media", track[0], artist=track[1], colors=colors)


class LinuxMedia(Source):
    name = "media"

    def run(self):
        try:
            asyncio.run(self._main())
        except Exception as e:
            self.error = f"media: {e}"

    async def _main(self):
        from dbus_next.aio import MessageBus
        from dbus_next import Message
        bus = await MessageBus().connect()
        await bus.call(Message(destination="org.freedesktop.DBus", path="/org/freedesktop/DBus",
                               interface="org.freedesktop.DBus", member="AddMatch", signature="s",
                               body=["type='signal',interface='org.freedesktop.DBus.Properties',"
                                     "path='/org/mpris/MediaPlayer2'"]))
        last = None

        def handler(msg):
            nonlocal last
            if msg.member != "PropertiesChanged" or len(msg.body) < 2:
                return
            meta = msg.body[1].get("Metadata")
            if not meta:
                return
            meta = meta.value
            title = meta.get("xesam:title").value if "xesam:title" in meta else None
            if title and title != last:
                last = title
                colors = None
                art = meta.get("mpris:artUrl")
                if art and art.value.startswith("file://"):
                    try:
                        colors = _art_colors(open(art.value[7:], "rb").read())
                    except OSError:
                        pass
                self.emit("media", title, colors=colors)

        bus.add_message_handler(handler)
        while not self.stopped.is_set():
            await asyncio.sleep(0.5)


def create(emit):
    if WINDOWS:
        return WindowsMedia(emit)
    if LINUX:
        return LinuxMedia(emit)
    return None
