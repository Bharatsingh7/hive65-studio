"""Minimal xdg-desktop-portal ScreenCast client (Hyprland, GNOME, KDE).

Returns (pipewire_fd, node_id) for GStreamer's pipewiresrc. The restore token
is stored next to the settings so the picker only appears once.
"""
import asyncio
import random

from ..settings import config_dir

TOKEN_FILE = config_dir() / "screencast.token"
BUS, PATH = "org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop"


async def _open():
    from dbus_next import Variant
    from dbus_next.aio import MessageBus
    from dbus_next.constants import BusType

    bus = await MessageBus(bus_type=BusType.SESSION, negotiate_unix_fd=True).connect()
    intro = await bus.introspect(BUS, PATH)
    portal = bus.get_proxy_object(BUS, PATH, intro).get_interface("org.freedesktop.portal.ScreenCast")
    sender = bus.unique_name[1:].replace(".", "_")
    from dbus_next import Message
    await bus.call(Message(destination="org.freedesktop.DBus", path="/org/freedesktop/DBus",
                           interface="org.freedesktop.DBus", member="AddMatch", signature="s",
                           body=["type='signal',interface='org.freedesktop.portal.Request',"
                                 "member='Response'"]))

    async def request(call, *args, options):
        token = f"hive65_{random.randint(0, 1 << 30)}"
        options["handle_token"] = Variant("s", token)
        req_path = f"/org/freedesktop/portal/desktop/request/{sender}/{token}"
        fut = asyncio.get_running_loop().create_future()

        def on_response(msg):
            if msg.path == req_path and msg.member == "Response" and not fut.done():
                fut.set_result(msg.body)

        bus.add_message_handler(on_response)
        await call(*args, options)
        code, results = await asyncio.wait_for(fut, 120)
        bus.remove_message_handler(on_response)
        if code != 0:
            raise RuntimeError("screen capture was cancelled or denied")
        return results

    res = await request(portal.call_create_session,
                        options={"session_handle_token": Variant("s", "hive65")})
    session = res["session_handle"].value
    opts = {"types": Variant("u", 1), "multiple": Variant("b", False),
            "cursor_mode": Variant("u", 1), "persist_mode": Variant("u", 2)}
    if TOKEN_FILE.exists():
        opts["restore_token"] = Variant("s", TOKEN_FILE.read_text().strip())
    await request(portal.call_select_sources, session, options=opts)
    res = await request(portal.call_start, session, "", options={})
    if "restore_token" in res:
        TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_FILE.write_text(res["restore_token"].value)
    node = res["streams"].value[0][0]
    fd = await portal.call_open_pipe_wire_remote(session, {})
    return fd, node, bus


_keepalive = []


def open_screencast():
    loop = asyncio.new_event_loop()
    fd, node, bus = loop.run_until_complete(_open())
    _keepalive.append((loop, bus))  # the session lives as long as the bus connection
    return fd, node
