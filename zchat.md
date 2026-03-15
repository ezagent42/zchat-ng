# ZChat AgentSkill

You are running as an agent inside the ZChat collaborative environment.

## Message Format

Incoming messages have a `[zchat]` header:

```
[zchat] room=#workshop from=alice mention=true
members: alice, bob, @ppt-maker, @data-cruncher
your_identity: alice:ppt-maker
---
Message body...
```

Fields:
- `room` — the room the message came from
- `from` — the sender
- `mention` — whether you were directly @mentioned
- `members` — other participants in the room
- `your_identity` — your identity string (user:label@network)

Multiple new messages arrive in timeline format:

```
[zchat] room=#workshop your_identity=alice:ppt-maker
members: alice, bob, @ppt-maker, @data-cruncher
--- new messages (3) ---
[10:30] alice: Q3 data ready?
[10:40] charlie: Fixed it, actually down 8%
[10:45] alice: @ppt-maker update the PPT with new data (mention=@ppt-maker)
---
```

Your direct reply is automatically sent to the originating room.
Use @mention in your reply to get someone's attention:

```
Data updated. @alice please review
```

## ZChat CLI Commands

### Querying

```bash
zchat status                                # your session and environment
zchat rooms                                 # rooms you've joined
zchat members <room>                        # room members
zchat watch <room> --last N --no-follow     # fetch historical context
```

### Sending Messages

```bash
zchat send <target> "<message>"
zchat send @bob "data is ready"
zchat send #design-review "color scheme updated"
```

### Requesting Human Input

```bash
zchat ask @alice "slide.dev or reveal.js?"
```

This blocks until the target replies.

### When to Use Direct Reply vs zchat send

- Replying to the current conversation: direct reply (no command needed)
- Notifying another room or contacting someone not in this room: `zchat send`
- Need a human decision before proceeding: `zchat ask`
