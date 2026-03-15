"""ZChat CLI — Typer-based command-line interface."""

from __future__ import annotations

import asyncio
import json
from typing import Optional

import typer

from zchat_cli.api import ZChatCLI
from zchat_cli.ext_registry import ExtensionRegistry
from zchat_cli.preflight import run_preflight
from zchat_protocol import ZChatEvent

# ── Typer apps ───────────────────────────────────────────────────────────

app = typer.Typer(name="zchat", help="ZChat-NG CLI")

room_app = typer.Typer(name="room", help="Room management")
session_app = typer.Typer(name="session", help="Session management")
template_app = typer.Typer(name="template", help="Template management")
agent_app = typer.Typer(name="agent", help="Agent configuration")
ext_app = typer.Typer(name="ext", help="Extension management")

app.add_typer(room_app)
app.add_typer(session_app)
app.add_typer(template_app)
app.add_typer(agent_app)
app.add_typer(ext_app)

# ── Shared extension registry ───────────────────────────────────────────

_ext_registry = ExtensionRegistry()

# ── Helpers ──────────────────────────────────────────────────────────────


def _run(coro):
    """Bridge sync Typer commands to async ZChatCLI methods."""
    return asyncio.run(coro)


def _get_cli() -> ZChatCLI:
    """Create a ZChatCLI backed by mock backends (for phase-0 skeleton)."""
    from zchat_com.mock import MockComBackend
    from zchat_acp.mock import MockAcpBackend

    com = MockComBackend()
    acp = MockAcpBackend()
    return ZChatCLI(com=com, acp=acp)


def _print_event(event: ZChatEvent) -> None:
    """Format and print a ZChatEvent for terminal output."""
    type_str = event.type.value
    typer.echo(f"[{type_str}] {event.from_}: {event.content}")


# ── Top-level commands ───────────────────────────────────────────────────


@app.command()
def doctor() -> None:
    """Run diagnostic checks."""
    cli = _get_cli()
    report = _run(cli.doctor())
    for check, passed in report.checks.items():
        status = "OK" if passed else "FAIL"
        typer.echo(f"  {check}: {status}")
    for msg in report.messages:
        typer.echo(f"  {msg}")
    if report.ok:
        typer.echo("All checks passed.")
    else:
        typer.echo("Some checks failed.")
        raise typer.Exit(code=1)


@app.command()
def status(
    session: Optional[str] = typer.Argument(None, help="Session to inspect"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show identity, network, peers, and sessions."""
    cli = _get_cli()

    identity = _run(cli.com.get_identity())
    network = _run(cli.com.get_network())
    peers = _run(cli.com.get_peers())
    sessions = _run(cli.acp.sessions())

    if as_json:
        data = {
            "identity": str(identity),
            "network": {"name": network.name, "online": network.online},
            "peers": [str(p) for p in peers],
            "sessions": [
                {"id": s.session_id, "agent": str(s.agent), "status": s.status}
                for s in sessions
            ],
        }
        typer.echo(json.dumps(data, indent=2))
        return

    typer.echo(f"Identity: {identity}")
    typer.echo(f"Network:  {network.name} (online={network.online})")
    typer.echo(f"Peers:    {len(peers)}")
    typer.echo(f"Sessions: {len(sessions)}")


@app.command()
def preflight() -> None:
    """Check prerequisites (python3, gh, claude)."""
    result = run_preflight()
    for tool, found in result.checks.items():
        status = "found" if found else "NOT FOUND"
        typer.echo(f"  {tool}: {status}")
    if result.ok:
        typer.echo("All prerequisites met.")
    else:
        typer.echo("Some prerequisites missing.")
        raise typer.Exit(code=1)


@app.command()
def network() -> None:
    """Show network info."""
    cli = _get_cli()
    net = _run(cli.com.get_network())
    typer.echo(f"Network: {net.name}")
    typer.echo(f"Peers:   {net.peer_count}")
    typer.echo(f"Online:  {net.online}")


@app.command()
def peers() -> None:
    """List connected peers."""
    cli = _get_cli()
    peer_list = _run(cli.com.get_peers())
    if not peer_list:
        typer.echo("No peers.")
        return
    for p in peer_list:
        typer.echo(f"  {p}")


@app.command()
def rooms() -> None:
    """List available rooms."""
    cli = _get_cli()
    room_list = _run(cli.rooms())
    if not room_list:
        typer.echo("No rooms.")
        return
    for r in room_list:
        typer.echo(f"  {r.name}  ({r.member_count} members)  {r.topic}")


@app.command()
def members(
    room: str = typer.Argument(..., help="Room name (e.g. #general)"),
) -> None:
    """List members of a room."""
    cli = _get_cli()
    member_list = _run(cli.members(room))
    if not member_list:
        typer.echo(f"No members in {room}.")
        return
    for m in member_list:
        typer.echo(f"  {m}")


@app.command()
def send(
    target: str = typer.Argument(..., help="Target room or identity"),
    message: str = typer.Argument(..., help="Message text"),
) -> None:
    """Send a message to a target."""
    cli = _get_cli()
    _run(cli.send(target, message))
    typer.echo(f"Sent to {target}")


@app.command()
def watch(
    room: Optional[str] = typer.Argument(None, help="Room to watch"),
    last: Optional[int] = typer.Option(None, "--last", "-n", help="Show last N events"),
    no_follow: bool = typer.Option(False, "--no-follow", help="Don't stream live"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Include tool events"),
    thinking: bool = typer.Option(False, "--thinking", help="Include thinking events"),
    show_all: bool = typer.Option(False, "--all", help="Show all event types"),
    from_participant: Optional[str] = typer.Option(None, "--from", help="Filter by sender"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
    since: Optional[str] = typer.Option(None, "--since", help="Show events since time"),
) -> None:
    """Watch events in a room."""
    cli = _get_cli()
    target_room = room or "#general"

    async def _watch():
        async for event in cli.watch(
            target_room,
            last=last,
            no_follow=no_follow,
            verbose=verbose,
            thinking=thinking,
            show_all=show_all,
        ):
            if from_participant and event.from_ != from_participant:
                continue
            if as_json:
                typer.echo(json.dumps(event.to_dict()))
            else:
                _print_event(event)

    _run(_watch())


@app.command()
def ask(
    target: str = typer.Argument(..., help="Target identity or room"),
    question: str = typer.Argument(..., help="Question to ask"),
    timeout: float = typer.Option(30.0, "--timeout", "-t", help="Timeout in seconds"),
) -> None:
    """Ask a question and wait for an answer."""
    cli = _get_cli()
    try:
        answer_event = _run(cli.ask(target, question, timeout=timeout))
        typer.echo(f"Answer: {answer_event.content}")
    except TimeoutError:
        typer.echo("Timed out waiting for answer.")
        raise typer.Exit(code=1)


@app.command()
def answer(
    text: str = typer.Argument(..., help="Answer text"),
    ask_id: Optional[str] = typer.Argument(None, help="ID of the ASK event"),
) -> None:
    """Reply to a pending ASK event."""
    if not ask_id:
        typer.echo("No ask_id provided; nothing to answer.")
        raise typer.Exit(code=1)
    cli = _get_cli()
    _run(cli.answer(ask_id, text))
    typer.echo("Answered.")


@app.command()
def spawn(
    agent_name: Optional[str] = typer.Argument(None, help="Agent name to spawn"),
    template: Optional[str] = typer.Option(None, "--template", "-t", help="Template name"),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="Custom agent name"),
    resume: bool = typer.Option(False, "--resume", help="Resume an existing session"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    """Spawn an agent."""
    effective_name = agent_name or name or "default-agent"
    cli = _get_cli()

    if not yes:
        typer.confirm(f"Spawn agent '{effective_name}'?", abort=True)

    if template:
        identity = _run(cli.spawn_adhoc(template, effective_name))
    else:
        identity = _run(cli.spawn(effective_name))
    typer.echo(f"Spawned {effective_name} as {identity}")


@app.command()
def sessions() -> None:
    """List active sessions."""
    cli = _get_cli()
    session_list = _run(cli.acp.sessions())
    if not session_list:
        typer.echo("Sessions: 0")
        return
    typer.echo(f"Sessions: {len(session_list)}")
    for s in session_list:
        typer.echo(f"  {s.session_id}  {s.agent}  {s.status}")


# ── room subcommands ─────────────────────────────────────────────────────


@room_app.command()
def create(
    name: str = typer.Argument(..., help="Room name"),
    topic: str = typer.Option("", "--topic", help="Room topic"),
) -> None:
    """Create a new room."""
    cli = _get_cli()
    room = _run(cli.com.room_create(name, topic))
    typer.echo(f"Created room {room.name}")


@room_app.command()
def invite(
    room: str = typer.Argument(..., help="Room name"),
    identity: str = typer.Argument(..., help="Identity to invite"),
) -> None:
    """Invite someone to a room."""
    from zchat_protocol import Identity as IdType

    cli = _get_cli()
    _run(cli.com.room_invite(room, IdType.parse(identity)))
    typer.echo(f"Invited {identity} to {room}")


@room_app.command()
def leave(
    room: str = typer.Argument(..., help="Room to leave"),
) -> None:
    """Leave a room."""
    cli = _get_cli()
    _run(cli.com.room_leave(room))
    typer.echo(f"Left {room}")


# ── session subcommands ──────────────────────────────────────────────────


@session_app.command()
def attach(
    session_id: str = typer.Argument(..., help="Session ID"),
) -> None:
    """Attach to an agent session."""
    cli = _get_cli()
    _run(cli.session_attach(session_id))
    typer.echo(f"Attached to {session_id}")


@session_app.command()
def detach(
    session_id: str = typer.Argument(..., help="Session ID"),
) -> None:
    """Detach from an agent session."""
    cli = _get_cli()
    _run(cli.session_detach(session_id))
    typer.echo(f"Detached from {session_id}")


@session_app.command()
def kill(
    session_id: str = typer.Argument(..., help="Session ID to kill"),
    force: bool = typer.Option(False, "--force", "-f", help="Force kill"),
) -> None:
    """Kill an agent session."""
    cli = _get_cli()
    _run(cli.acp.kill_session(session_id))
    typer.echo(f"Killed session {session_id}")


# ── template subcommands ─────────────────────────────────────────────────


@template_app.command("init")
def template_init(
    name: str = typer.Argument(..., help="Template name"),
) -> None:
    """Initialize a new template."""
    cli = _get_cli()
    _run(cli.template_init(name))
    typer.echo(f"Initialized template {name}")


@template_app.command("list")
def template_list() -> None:
    """List available templates."""
    cli = _get_cli()
    templates = _run(cli.template_list())
    if not templates:
        typer.echo("No templates.")
        return
    for t in templates:
        typer.echo(f"  {t.name}  {t.description}")


# ── agent subcommands ────────────────────────────────────────────────────


@agent_app.command("init")
def agent_init(
    name: str = typer.Argument("default", help="Agent config name"),
    from_template: Optional[str] = typer.Option(None, "--from", help="Base template"),
) -> None:
    """Initialize an agent configuration."""
    cli = _get_cli()
    _run(cli.agent_init(name))
    typer.echo(f"Initialized agent config {name}")


@agent_app.command("list")
def agent_list() -> None:
    """List agent configurations."""
    cli = _get_cli()
    agents = _run(cli.agent_list())
    if not agents:
        typer.echo("No agent configs.")
        return
    for a in agents:
        typer.echo(f"  {a.name}  template={a.template}")


# ── ext subcommands ──────────────────────────────────────────────────────


@ext_app.command()
def install(
    name: str = typer.Argument(..., help="Extension name"),
) -> None:
    """Install an extension."""
    info = _ext_registry.install(name)
    typer.echo(f"Installed extension {info.name}")


@ext_app.command()
def uninstall(
    name: str = typer.Argument(..., help="Extension name"),
) -> None:
    """Uninstall an extension."""
    _ext_registry.uninstall(name)
    typer.echo(f"Uninstalled extension {name}")


@ext_app.command("list")
def ext_list() -> None:
    """List installed extensions."""
    extensions = _ext_registry.list()
    if not extensions:
        typer.echo("No extensions installed.")
        return
    for ext in extensions:
        typer.echo(f"  {ext.name}  v{ext.version}  enabled={ext.enabled}")


# ── Entry point ──────────────────────────────────────────────────────────


def main() -> None:
    """CLI entry point."""
    app()


if __name__ == "__main__":
    main()
